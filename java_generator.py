"""
java_generator.py
-----------------
Generates a Java source file (JDBC) that inserts a mapped JSON payload
into the PostgreSQL `user` table. Uses OpenAI to produce idiomatic Java
code given the mapping and a description of the DB schema.

Function: generate_insert_java(mapped: Dict[str,str], schema: Dict[str,str], table_name: str='user')
returns: (path, source)
"""
import os
import json
from datetime import datetime
from typing import Dict, Tuple
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _build_schema_text(schema: Dict[str, str], table_name: str) -> str:
    lines = [f"- {col}: {desc}" for col, desc in schema.items()]
    return f"Table `{table_name}` columns:\n" + "\n".join(lines)


def generate_insert_java(mapped: Dict[str, str], schema: Dict[str, str], table_name: str = "user") -> Tuple[str, str]:
    """
    Ask the LLM to produce a Java class that inserts the provided `mapped`
    values into `table_name` using a prepared statement (JDBC). The LLM
    receives the schema description so it knows which columns to target.

    Saves the returned Java source to `generated_java/Insert{Table}_{ts}.java`
    and returns (path, source).
    """
    schema_text = _build_schema_text(schema, table_name)

    # Prepare deterministic classname to request from the LLM and the
    # filename we will write. We will also enforce the classname in the
    # returned source to make it runnable with `javac`/`java`.
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    class_name = f"Insert{table_name.capitalize()}_{ts}"
    filename = f"{class_name}.java"

    system = (
        "You are a senior Java developer. Produce exactly one Java source file"
        " that defines a public class with the NAME provided (see user message)."
        " The class must use JDBC (PreparedStatement) to insert the provided fields"
        " into the target PostgreSQL table. Handle nulls safely, use `try-with-resources`,"
        " and do NOT output any explanatory text or markdown — only the Java source.")

    # Build a list of columns in order (to match with data values) and quote them for SQL
    cols_ordered = list(mapped.keys())
    quoted_cols = [f'"{col}"' for col in cols_ordered]
    placeholders = ", ".join(["?"] * len(cols_ordered))
    col_names_quoted = ", ".join(quoted_cols)
    col_names = ", ".join(cols_ordered)

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "speed_builder")
        db_url = f"jdbc:postgresql://{db_host}:{db_port}/{db_name}"
    db_user = os.getenv("DB_USER") or os.getenv("DB_USERNAME") or "postgres"
    db_pass = os.getenv("DB_PASS") or os.getenv("DB_PASSWORD") or "admin"

    user_prompt = (
        f"Generate a Java source file whose public class name is: {class_name}.\n"
        "Requirements:\n"
        "- The class must be public and its filename must match the class name exactly.\n"
        "- Include imports: java.sql.*, java.util.Map.\n"
        "- Hardcode the JDBC connection values directly in the generated source with these exact values:\n"
        f"  * String url = \"{db_url}\"\n"
        f"  * String user = \"{db_user}\"\n"
        f"  * String pass = \"{db_pass}\"\n"
        "- Do not use System.getenv() or any environment variables at runtime. The generated class must run directly after compilation.\n"
        "- Try to load the PostgreSQL driver: Class.forName(\"org.postgresql.Driver\"); (catch ClassNotFoundException)\n"
        "- Provide a public static method `insert(Map<String,String> data)` that:\n"
        "  * Uses the hardcoded JDBC values from above\n"
        "  * Opens a JDBC connection using DriverManager.getConnection(url, user, pass)\n"
        "  * Executes a PreparedStatement INSERT with the following EXACT column order and names:\n"
        f'    INSERT INTO \\"{table_name}\\" ({col_names_quoted}) VALUES ({placeholders})\n'
        "    (Note: quote both the table name and all column names to handle reserved keywords and case sensitivity)\n"
        "  * Sets each parameter using the corresponding mapped data key from the Map (in order)\n"
        "  * Uses try-with-resources for Connection and PreparedStatement\n"
        "- Include robust error handling: catch SQLException and print stacktrace; do not silently fail.\n"
        "- Provide a `public static void main(String[] args)` that creates a Map with the mapped JSON and calls insert().\n"
        "- Target table/columns/descriptions:\n\n"
        f"{schema_text}\n\n"
        "Mapped JSON keys and example values (MUST match these keys in order):\n"
        + json.dumps(mapped, indent=2)
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_prompt},
        ],
    )

    src = response.choices[0].message.content

    # Post-process to ensure the declared public class matches our filename.
    import re
    if not re.search(rf"public\s+class\s+{re.escape(class_name)}", src):
        # Replace the first public class declaration name if present
        if re.search(r"public\s+class\s+\w+", src):
            src = re.sub(r"public\s+class\s+\w+", f"public class {class_name}", src, count=1)
        else:
            # If no public class present, wrap the source by adding a simple
            # public class that delegates to the LLM-provided insert implementation
            wrapper = []
            wrapper.append(f"public class {class_name} {{\n")
            wrapper.append("    // The generated insert implementation follows.\n")
            # Indent original source
            for line in src.splitlines():
                wrapper.append("    " + line + "\n")
            wrapper.append("}\n")
            src = "".join(wrapper)

    # Ensure Map import exists and there's a main method. If main missing, append one.
    if "import java.util.Map" not in src:
        src = src.replace("import java.sql.PreparedStatement;", "import java.sql.PreparedStatement;\nimport java.util.Map;", 1)

    if "public static void main" not in src:
        # Create a compact main that uses Map.of for the mapped values
        entries = []
        for k, v in mapped.items():
            safe_v = v.replace('"', '\\"')
            entries.append(f'"{k}", "{safe_v}"')
        map_of = "Map.of(" + ", ".join(entries) + ")" if entries else "Map.of()"
        main_block = f"\n    public static void main(String[] args) {{\n        Map<String,String> data = {map_of};\n        insert(data);\n    }}\n"
        # Append before final closing brace if present
        if src.rstrip().endswith('}'):
            src = src.rstrip()[:-1] + main_block + "}\n"
        else:
            src += "\n" + main_block

    # Ensure output directory exists
    out_dir = os.path.join(os.getcwd(), "generated_java")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)

    return path, src

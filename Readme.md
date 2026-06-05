source env/Scripts/activate

uvicorn main:app --reload --port 8000

cd generated_java
javac -cp ".;../postgresql-42.6.0.jar" InsertUser_20260605T132359Z.java
java -cp ".;../postgresql-42.6.0.jar" InsertUser_20260605T132359Z
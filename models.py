from sqlalchemy import Column, Integer, String
from database import Base


class User(Base):
    __tablename__ = "user"

    id          = Column(Integer, primary_key=True, index=True, autoincrement=True)
    Name        = Column(String, nullable=False)
    Email       = Column(String, unique=True, nullable=False)
    Phone_Number = Column(String, nullable=False)
    Address     = Column(String, nullable=False)
    National_ID = Column(String, unique=True, nullable=False)
    Date_of_Birth = Column(String, nullable=False)

    def to_dict(self):
        return {
            "id":            self.id,
            "Name":          self.Name,
            "Email":         self.Email,
            "Phone_Number":  self.Phone_Number,
            "Address":       self.Address,
            "National_ID":   self.National_ID,
            "Date_of_Birth": self.Date_of_Birth,
        }

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .db import Base

class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True, index=True)
    summary = Column(String, unique=True, nullable=False)
    lessons = relationship('Lesson', back_populates='student')

class Lesson(Base):
    __tablename__ = 'lessons'
    id = Column(Integer, primary_key=True, index=True)
    event_uid = Column(String, unique=True, index=True)
    summary = Column(String)
    start = Column(DateTime)
    end = Column(DateTime)
    description = Column(Text)
    student_id = Column(Integer, ForeignKey('students.id'))
    student = relationship('Student', back_populates='lessons')

class TgLink(Base):
    __tablename__ = 'tg_links'
    id = Column(Integer, primary_key=True)
    tg_user_id = Column(String, index=True)
    student_id = Column(Integer, ForeignKey('students.id'))
    UniqueConstraint('tg_user_id', 'student_id', name='uix_tg_student')

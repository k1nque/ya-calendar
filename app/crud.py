from sqlalchemy.orm import Session
from . import models

def get_or_create_student(db: Session, summary: str):
    s = db.query(models.Student).filter_by(summary=summary).first()
    if s:
        return s
    s = models.Student(summary=summary)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s

def upsert_lesson(db: Session, event_uid: str, summary: str, start, end, description, student: models.Student):
    l = db.query(models.Lesson).filter_by(event_uid=event_uid).first()
    if l:
        changed = False
        if l.start != start or l.end != end or l.description != description or l.summary != summary or l.student_id != student.id:
            l.start = start
            l.end = end
            l.description = description
            l.summary = summary
            l.student = student
            changed = True
        if changed:
            db.add(l)
            db.commit()
            db.refresh(l)
        return l, changed
    l = models.Lesson(event_uid=event_uid, summary=summary, start=start, end=end, description=description, student=student)
    db.add(l)
    db.commit()
    db.refresh(l)
    return l, True

def create_tg_link(db: Session, tg_user_id: str, student_id: int):
    link = db.query(models.TgLink).filter_by(tg_user_id=str(tg_user_id), student_id=student_id).first()
    if link:
        return link
    link = models.TgLink(tg_user_id=str(tg_user_id), student_id=student_id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link

def get_links_for_student(db: Session, student_id: int):
    return db.query(models.TgLink).filter_by(student_id=student_id).all()

def get_lesson(db: Session, lesson_id: int):
    return db.query(models.Lesson).filter_by(id=lesson_id).first()

def list_students(db: Session):
    return db.query(models.Student).order_by(models.Student.summary).all()

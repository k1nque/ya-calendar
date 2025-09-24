from sqlalchemy.orm import Session
from . import models


def get_student_by_id(db: Session, student_id: int):
    return db.query(models.Student).filter_by(id=student_id).first()


def get_or_create_student(db: Session, summary: str):
    s = db.query(models.Student).filter_by(summary=summary).first()
    if s:
        return s
    s = models.Student(summary=summary)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def upsert_lesson(
    db: Session, event_uid: str, summary: str, start, end, student: models.Student
):
    l = db.query(models.Lesson).filter_by(event_uid=event_uid).first()
    if l:
        changed = False
        if (
            l.start != start
            or l.end != end
            or l.summary != summary
            or l.student_id != student.id
        ):
            l.start = start
            l.end = end
            l.summary = summary
            l.student = student
            changed = True
        if changed:
            db.add(l)
            db.commit()
            db.refresh(l)
        return l, changed
    l = models.Lesson(
        event_uid=event_uid,
        summary=summary,
        start=start,
        end=end,
        student=student,
    )
    db.add(l)
    db.commit()
    db.refresh(l)
    return l, True


def create_tg_link(db: Session, tg_user_id: str, student_id: int):
    link = (
        db.query(models.TgLink).filter_by(tg_user_id=str(tg_user_id), student_id=student_id).first()
    )
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


def get_student_by_tg_user_id(db: Session, tg_user_id: str):
    link = db.query(models.TgLink).filter_by(tg_user_id=tg_user_id).first()
    return db.query(models.Student).filter_by(id=link.student_id).first() if link else None

def get_student_summary_by_id(db: Session, student_id: int):
    """Получить только summary ученика по ID"""
    result = db.query(models.Student.summary).filter_by(id=student_id).first()
    return result[0] if result else None


def toggle_student_active_status(db: Session, student_id: int):
    """Переключить статус активности ученика"""
    student = db.query(models.Student).filter_by(id=student_id).first()
    if student:
        student.is_active = not student.is_active
        db.add(student)
        db.commit()
        db.refresh(student)
        return student
    return None


def update_student_paid_lessons(db: Session, student_id: int, paid_lessons_count: int):
    """Обновить количество оплаченных занятий"""
    student = db.query(models.Student).filter_by(id=student_id).first()
    if student:
        student.paid_lessons_count = paid_lessons_count
        db.add(student)
        db.commit()
        db.refresh(student)
        return student
    return None


def mark_lesson_paid(db: Session, lesson_id: int, is_paid: bool = True):
    """Отметить занятие как оплаченное или неоплаченное"""
    lesson = db.query(models.Lesson).filter_by(id=lesson_id).first()
    if lesson:
        lesson.is_paid = is_paid
        db.add(lesson)
        db.commit()
        db.refresh(lesson)
        return lesson
    return None


def deduct_paid_lesson(db: Session, student_id: int):
    """Списать одно оплаченное занятие у ученика (если есть)"""
    student = db.query(models.Student).filter_by(id=student_id).first()
    if student and student.paid_lessons_count > 0:
        student.paid_lessons_count -= 1
        db.add(student)
        db.commit()
        db.refresh(student)
        return student
    return None

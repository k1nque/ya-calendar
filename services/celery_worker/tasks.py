import requests
from celery_app import celery
from app.db import SessionLocal
from app import crud


@celery.task(bind=True, name='tasks.send_notify')
def send_notify(self, lesson_id: int):
    """Call bot service HTTP endpoint to notify users about lesson_id"""
    url = "http://bot:8080/notify"
    try:
        resp = requests.post(url, json={"lesson_id": lesson_id}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        raise self.retry(exc=e, countdown=60)
    return True


@celery.task(bind=True, name='tasks.deduct_lesson_after_completion')
def deduct_lesson_after_completion(self, lesson_id: int):
    """Списать одно оплаченное занятие после завершения урока"""
    db = SessionLocal()
    try:
        lesson = crud.get_lesson(db, lesson_id)
        if not lesson:
            return {"success": False, "error": "lesson not found"}
        
        # Списываем оплаченное занятие у ученика
        student = crud.deduct_paid_lesson(db, lesson.student_id)
        if student:
            return {
                "success": True, 
                "student_id": lesson.student_id,
                "remaining_lessons": student.paid_lessons_count
            }
        else:
            return {
                "success": False, 
                "error": "no paid lessons to deduct or student not found"
            }
    except Exception as e:
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()

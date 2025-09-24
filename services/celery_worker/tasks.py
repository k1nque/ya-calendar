import requests
from celery_app import celery
from app.db import SessionLocal
from app import crud


def send_admin_notification(message: str):
    """Отправить уведомление админу через bot API"""
    try:
        url = "http://bot:8080/admin_notify"
        resp = requests.post(url, json={"message": message}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        # Игнорируем ошибки отправки админу, это не критично
        return False


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
    """Списать одно оплаченное занятие после завершения урока и отметить урок как оплаченный"""
    db = SessionLocal()
    try:
        lesson = crud.get_lesson(db, lesson_id)
        if not lesson:
            return {"success": False, "error": "lesson not found"}
        
        # Отмечаем урок как оплаченный
        paid_lesson = crud.mark_lesson_paid(db, lesson_id, is_paid=True)
        
        # Списываем оплаченное занятие у ученика
        student = crud.deduct_paid_lesson(db, lesson.student_id)
        
        if student and paid_lesson:
            return {
                "success": True, 
                "student_id": lesson.student_id,
                "remaining_lessons": student.paid_lessons_count,
                "lesson_marked_paid": True
            }
        elif paid_lesson and not student:
            # Отправляем уведомление админу о том, что у ученика закончились оплаченные занятия
            student_info = crud.get_student_by_id(db, lesson.student_id)
            student_name = student_info.summary if student_info else "Неизвестный ученик"
            
            warning_message = (
                f"⚠️ Внимание!\n\n"
                f"У ученика {student_name} закончились оплаченные занятия.\n"
                f"Урок '{lesson.summary}' завершился, но списать занятие не удалось.\n"
                f"Урок отмечен как оплаченный.\n\n"
                f"Рекомендуется пополнить баланс ученика через /payment"
            )
            
            send_admin_notification(warning_message)
            
            return {
                "success": True,
                "student_id": lesson.student_id, 
                "remaining_lessons": 0,
                "lesson_marked_paid": True,
                "warning": "no paid lessons to deduct, but lesson marked as paid",
                "admin_notified": True
            }
        else:
            return {
                "success": False, 
                "error": "failed to mark lesson as paid or student not found"
            }
    except Exception as e:
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()

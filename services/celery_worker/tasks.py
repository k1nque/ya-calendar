import requests
import logging
from celery_app import celery
from app.db import SessionLocal
from app import crud

# Получаем logger для задач
logger = logging.getLogger('celery_worker')


def send_admin_notification(message: str):
    """Отправить уведомление админу через bot API"""
    try:
        logger.debug("Sending admin notification")
        url = "http://bot:8080/admin_notify"
        resp = requests.post(url, json={"message": message}, timeout=10)
        resp.raise_for_status()
        logger.info("Admin notification sent successfully")
        return True
    except Exception as e:
        # Игнорируем ошибки отправки админу, это не критично
        logger.warning(f"Failed to send admin notification: {e}")
        return False


@celery.task(bind=True, name='tasks.send_notify')
def send_notify(self, lesson_id: int):
    """Call bot service HTTP endpoint to notify users about lesson_id"""
    logger.info(f"Starting notification task for lesson_id={lesson_id}")
    url = "http://bot:8080/notify"
    try:
        resp = requests.post(url, json={"lesson_id": lesson_id}, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"Notification sent for lesson_id={lesson_id}: {result}")
        return True
    except Exception as e:
        logger.error(f"Failed to send notification for lesson_id={lesson_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60)


@celery.task(bind=True, name='tasks.deduct_lesson_after_completion')
def deduct_lesson_after_completion(self, lesson_id: int):
    """Списать одно оплаченное занятие после завершения урока и отметить урок как оплаченный"""
    logger.info(f"Starting deduction task for lesson_id={lesson_id}")
    db = SessionLocal()
    try:
        lesson = crud.get_lesson(db, lesson_id)
        if not lesson:
            logger.warning(f"Lesson not found: lesson_id={lesson_id}")
            return {"success": False, "error": "lesson not found"}
        
        logger.info(f"Processing lesson completion: {lesson.summary} for student_id={lesson.student_id}")
        
        # Отмечаем урок как оплаченный
        paid_lesson = crud.mark_lesson_paid(db, lesson_id, is_paid=True)
        
        # Списываем оплаченное занятие у ученика
        student = crud.deduct_paid_lesson(db, lesson.student_id)
        
        if student and paid_lesson:
            logger.info(f"Successfully deducted lesson for student_id={lesson.student_id}, remaining={student.paid_lessons_count}")
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
            
            logger.warning(f"No paid lessons to deduct for student {student_name} (student_id={lesson.student_id})")
            
            warning_message = (
                f"⚠️ Внимание!\n\n"
                f"У ученика {student_name} закончились оплаченные занятия.\n"
                f"Урок '{lesson.summary}' завершился, но списать занятие не удалось.\n"
                f"Урок отмечен как оплаченный.\n\n"
                f"Рекомендуется пополнить баланс ученика через /payment"
            )
            
            send_admin_notification(warning_message)
            logger.info(f"Admin notification sent for student {student_name}")
            
            return {
                "success": True,
                "student_id": lesson.student_id, 
                "remaining_lessons": 0,
                "lesson_marked_paid": True,
                "warning": "no paid lessons to deduct, but lesson marked as paid",
                "admin_notified": True
            }
        else:
            logger.error(f"Failed to process lesson completion for lesson_id={lesson_id}")
            return {
                "success": False, 
                "error": "failed to mark lesson as paid or student not found"
            }
    except Exception as e:
        logger.error(f"Error in deduction task for lesson_id={lesson_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()

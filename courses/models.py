from django.db import models
from django.conf import settings


class Course(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="courses"
    )

    course_code = models.CharField(max_length=20)
    course_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.course_code} - {self.course_name}"


class CourseMaterial(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="materials"
    )

    title = models.CharField(max_length=255)

    file = models.FileField(
        upload_to="course_materials/"
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


# ============================================================
# FLASHCARD DECK
# ============================================================

class FlashcardDeck(models.Model):

    CARD_STYLE_CHOICES = [
        ("term", "Term to Definition"),
        ("q", "Question to Answer"),
        ("cloze", "Fill in the Blank"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="flashcard_decks"
    )

    material = models.ForeignKey(
        CourseMaterial,
        on_delete=models.CASCADE,
        related_name="flashcard_decks"
    )

    title = models.CharField(max_length=255)

    card_style = models.CharField(
        max_length=10,
        choices=CARD_STYLE_CHOICES,
        default="q"
    )

    total_cards = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.user}"


# ============================================================
# INDIVIDUAL FLASHCARDS
# ============================================================

class Flashcard(models.Model):

    deck = models.ForeignKey(
        FlashcardDeck,
        on_delete=models.CASCADE,
        related_name="cards"
    )

    front = models.TextField()

    back = models.TextField()

    is_known = models.BooleanField(default=False)

    review_count = models.PositiveIntegerField(default=0)

    position = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"Flashcard {self.position} - {self.deck.title}"

 
# ============================================================
# QUIZ
# ============================================================

class Quiz(models.Model):

    QUESTION_TYPE_CHOICES = [
        ("mcq", "Multiple Choice"),
        ("tf", "True or False"),
        ("sa", "Short Answer"),
        ("mixed", "Mixed"),
    ]

    DIFFICULTY_CHOICES = [
        ("Easy", "Easy"),
        ("Medium", "Medium"),
        ("Hard", "Hard"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quizzes"
    )

    material = models.ForeignKey(
        CourseMaterial,
        on_delete=models.CASCADE,
        related_name="quizzes"
    )

    title = models.CharField(max_length=255)

    question_type = models.CharField(
        max_length=10,
        choices=QUESTION_TYPE_CHOICES,
        default="mcq"
    )

    difficulty = models.CharField(
        max_length=10,
        choices=DIFFICULTY_CHOICES,
        default="Medium"
    )

    topic = models.CharField(
        max_length=255,
        default="All topics"
    )

    total_questions = models.PositiveIntegerField(default=0)

    # 0 means no time limit.
    time_limit_seconds = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.user}"


# ============================================================
# QUIZ QUESTION
# ============================================================

class QuizQuestion(models.Model):

    QUESTION_TYPE_CHOICES = [
        ("mcq", "Multiple Choice"),
        ("tf", "True or False"),
        ("sa", "Short Answer"),
    ]

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions"
    )

    question_type = models.CharField(
        max_length=10,
        choices=QUESTION_TYPE_CHOICES
    )

    question_text = models.TextField()

    # MCQ: ["A", "B", "C", "D"]
    # True/False: ["True", "False"]
    # Short answer: []
    options = models.JSONField(default=list)

    # MCQ / True-False: zero-based option index.
    # Short answer: model-answer text.
    correct_answer = models.JSONField()

    explanation = models.TextField()

    position = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]

        constraints = [
            models.UniqueConstraint(
                fields=["quiz", "position"],
                name="unique_quiz_question_position"
            )
        ]

    def __str__(self):
        return f"Question {self.position} - {self.quiz.title}"


# ============================================================
# QUIZ ATTEMPT
# ============================================================

class QuizAttempt(models.Model):

    STATUS_CHOICES = [
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
    ]

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="attempts"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_attempts"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="in_progress"
    )

    started_at = models.DateTimeField(auto_now_add=True)

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # Number of correctly answered questions.
    correct_answers = models.PositiveIntegerField(default=0)

    # Percentage score, such as 80.00.
    # Null means the attempt has not been graded.
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Actual quiz duration.
    time_taken_seconds = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return (
            f"Attempt {self.id} - "
            f"{self.quiz.title} - {self.user}"
        )


# ============================================================
# STUDENT QUIZ RESPONSE
# ============================================================

class QuizResponse(models.Model):

    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name="student_responses"
    )

    # MCQ / True-False: selected option index.
    # Short answer: student's written response.
    # Null represents an unanswered question.
    student_answer = models.JSONField(
        null=True,
        blank=True
    )

    # Null means not yet graded.
    is_correct = models.BooleanField(
        null=True,
        blank=True
    )

    # Optional feedback for short-answer grading.
    feedback = models.TextField(
        blank=True,
        default=""
    )

    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_response_per_attempt_question"
            )
        ]

    def __str__(self):
        return (
            f"Response {self.id} - "
            f"Attempt {self.attempt_id}"
        )
       


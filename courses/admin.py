from django.contrib import admin
from .models import Course, CourseMaterial


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "course_code",
        "course_name",
        "user",
        "created_at"
    )

    search_fields = (
        "course_code",
        "course_name"
    )


@admin.register(CourseMaterial)
class CourseMaterialAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "course",
        "uploaded_at"
    )

    search_fields = ("title",)
    list_filter = ("course",)

from django.contrib import admin
from django.contrib import messages
from django import forms
import csv
import re
import zipfile
from collections import defaultdict
from io import BytesIO, StringIO
import threading
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo
from .models import Course, CanvasUser, Category, Prompt, CourseSummary, Agent, UserCourse, UserCourseInteractionSummary, CourseClassSchedule
from django.db.models import Count, Subquery, OuterRef, Value, IntegerField, DateTimeField, TextField, Q
from django.db.models.functions import TruncDate
from django.db.models.functions import Coalesce
from datetime import timedelta
from django.utils import timezone
from django.contrib.admin import SimpleListFilter
from django.urls import reverse, path
from django.utils.html import format_html
from django.http import HttpResponse, HttpResponseRedirect
from urllib.parse import urlencode
from django.db import close_old_connections
from .services.prompt_analysis import analyze_prompt_interaction


LOCAL_TIME_ZONE = ZoneInfo("America/Santiago")


# Register your models here
class XlsxExportMixin:
    def _build_xlsx(self, rows, sheet_name="Sheet1"):
        workbook = BytesIO()
        with zipfile.ZipFile(workbook, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
            )
            archive.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
            )
            archive.writestr(
                "xl/workbook.xml",
                f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
            )
            archive.writestr("xl/worksheets/sheet1.xml", self._build_sheet_xml(rows))
        workbook.seek(0)
        return workbook

    def _build_sheet_xml(self, rows):
        xml_rows = []
        for row_number, row in enumerate(rows, start=1):
            cells = []
            for column_number, value in enumerate(row, start=1):
                cell_ref = f"{self._xlsx_column_name(column_number)}{row_number}"
                text = self._xlsx_text(value)
                cells.append(
                    f'<c r="{cell_ref}" t="inlineStr"><is>'
                    f'<t xml:space="preserve">{text}</t>'
                    f'</is></c>'
                )
            xml_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')

        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(xml_rows)}</sheetData>'
            '</worksheet>'
        )

    def _xlsx_column_name(self, column_number):
        name = ""
        while column_number:
            column_number, remainder = divmod(column_number - 1, 26)
            name = chr(65 + remainder) + name
        return name

    def _xlsx_text(self, value):
        text = str(value or "")
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return escape(text)

    def _format_datetime(self, value):
        if not value:
            return ""
        return timezone.localtime(value, LOCAL_TIME_ZONE).strftime("%Y-%m-%d %H:%M:%S")


class CourseClassScheduleInline(admin.TabularInline):
    model = CourseClassSchedule
    extra = 0
    fields = ("weekday", "start_time", "end_time", "active_from", "active_until")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    inlines = (CourseClassScheduleInline,)
    list_display = ('current_agent_display', 'canvas_id', 'title', 'created', 'created_by')
    search_fields = ('title',)
    list_filter = ('created',)
    ordering = ('-created',)

    @admin.display(description="Current agent", ordering="current_agent__name")
    def current_agent_display(self, obj):
        return obj.current_agent

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.groups.filter(name='Teachers').exists():
            qs = qs.filter(created_by=request.user)
        return qs
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by: # Only set if it hasnt been set.
             obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CourseClassSchedule)
class CourseClassScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "course",
        "weekday",
        "start_time",
        "end_time",
        "active_from",
        "active_until",
    )
    list_filter = ("course", "weekday")
    search_fields = ("course__title",)
    ordering = ("course__title", "weekday", "start_time")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("course")
        if request.user.groups.filter(name="Teachers").exists():
            qs = qs.filter(course__created_by=request.user)
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "course" and request.user.groups.filter(name="Teachers").exists():
            kwargs["queryset"] = Course.objects.filter(created_by=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(CanvasUser)
class CanvasUserAdmin(admin.ModelAdmin):
    list_display = ('canvas_id', 'login', 'created')
    search_fields = ('login',)
    list_filter = ('created',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created')
    search_fields = ('name',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.groups.filter(name='Teachers').exists():
            qs = qs.filter(created_by=request.user)
        return qs
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by: 
             obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Prompt)
class PromptAdmin(XlsxExportMixin, admin.ModelAdmin):
    change_list_template = "admin/chatbox/prompt/change_list.html"
    list_display = (
        'canvas_user',
        'course',
        'agent',
        'interaction_type',
        'answer_correctness',
        'interaction_analyzed_at',
        'created',
    )
    search_fields = ('prompt_text',)
    list_filter = ('interaction_type', 'answer_correctness', 'course', 'created')
    readonly_fields = ('interaction_analyzed_at', 'interaction_analysis_error')
    actions = ('export_prompts_as_csv', 'export_prompts_as_xlsx')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "export-csv/",
                self.admin_site.admin_view(self.export_filtered_prompts_as_csv),
                name="chatbox_prompt_export_csv",
            ),
            path(
                "export-xlsx/",
                self.admin_site.admin_view(self.export_filtered_prompts_as_xlsx),
                name="chatbox_prompt_export_xlsx",
            ),
        ]
        return custom_urls + urls
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.groups.filter(name='Teachers').exists():
            qs = qs.filter(course__created_by=request.user)
        return qs

    def changelist_view(self, request, extra_context=None):
        querystring = request.GET.urlencode()
        extra_context = extra_context or {}
        extra_context["export_csv_url"] = reverse("admin:chatbox_prompt_export_csv")
        extra_context["export_xlsx_url"] = reverse("admin:chatbox_prompt_export_xlsx")
        if querystring:
            extra_context["export_csv_url"] = f'{extra_context["export_csv_url"]}?{querystring}'
            extra_context["export_xlsx_url"] = f'{extra_context["export_xlsx_url"]}?{querystring}'
        return super().changelist_view(request, extra_context=extra_context)

    def _filtered_changelist_queryset(self, request):
        changelist = self.get_changelist_instance(request)
        return changelist.queryset

    def _export_queryset(self, queryset):
        return queryset.select_related(
            "canvas_user",
            "course",
            "agent",
            "category",
        ).order_by("created", "id")

    def _export_headers(self):
        return [
            "id",
            "created",
            "course_id",
            "course_canvas_id",
            "course_title",
            "canvas_user_id",
            "canvas_user_canvas_id",
            "canvas_user_login",
            "agent_id",
            "agent_name",
            "category",
            "prompt_text",
            "prompt_answer",
            "interaction_type",
            "answer_correctness",
            "interaction_analyzed_at",
            "interaction_analysis_error",
        ]

    def _export_rows(self, queryset):
        for prompt in self._export_queryset(queryset):
            yield [
                prompt.id,
                self._format_datetime(prompt.created),
                prompt.course_id,
                prompt.course.canvas_id if prompt.course else "",
                prompt.course.title if prompt.course else "",
                prompt.canvas_user_id,
                prompt.canvas_user.canvas_id if prompt.canvas_user else "",
                prompt.canvas_user.login if prompt.canvas_user else "",
                prompt.agent_id or "",
                prompt.agent.name if prompt.agent else "",
                prompt.category.name if prompt.category else "",
                prompt.prompt_text,
                prompt.prompt_answer,
                prompt.interaction_type or "",
                prompt.answer_correctness or "",
                self._format_datetime(prompt.interaction_analyzed_at),
                prompt.interaction_analysis_error or "",
            ]

    def _export_filename(self, extension):
        timestamp = timezone.localtime(timezone.now()).strftime("%Y%m%d-%H%M%S")
        return f"prompts-{timestamp}.{extension}"

    def export_filtered_prompts_as_csv(self, request):
        if not self.has_view_or_change_permission(request):
            messages.error(request, "No tienes permisos para exportar prompts.")
            return HttpResponseRedirect(reverse("admin:chatbox_prompt_changelist"))

        return self._prompts_csv_response(self._filtered_changelist_queryset(request))

    def export_filtered_prompts_as_xlsx(self, request):
        if not self.has_view_or_change_permission(request):
            messages.error(request, "No tienes permisos para exportar prompts.")
            return HttpResponseRedirect(reverse("admin:chatbox_prompt_changelist"))

        return self._prompts_xlsx_response(self._filtered_changelist_queryset(request))

    @admin.action(description="Descargar prompts seleccionados como CSV")
    def export_prompts_as_csv(self, request, queryset):
        return self._prompts_csv_response(queryset)

    @admin.action(description="Descargar prompts seleccionados como XLSX")
    def export_prompts_as_xlsx(self, request, queryset):
        return self._prompts_xlsx_response(queryset)

    def _prompts_csv_response(self, queryset):
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(self._export_headers())
        writer.writerows(self._export_rows(queryset))

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="{self._export_filename("csv")}"'
        )
        return response

    def _prompts_xlsx_response(self, queryset):
        headers = self._export_headers()
        rows = [headers, *self._export_rows(queryset)]
        workbook = self._build_xlsx(rows)

        response = HttpResponse(
            workbook.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{self._export_filename("xlsx")}"'
        )
        return response

    def _build_xlsx(self, rows):
        workbook = BytesIO()
        with zipfile.ZipFile(workbook, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
            )
            archive.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
            )
            archive.writestr(
                "xl/workbook.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Prompts" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
            )
            archive.writestr("xl/worksheets/sheet1.xml", self._build_sheet_xml(rows))
        workbook.seek(0)
        return workbook

    def _build_sheet_xml(self, rows):
        xml_rows = []
        for row_number, row in enumerate(rows, start=1):
            cells = []
            for column_number, value in enumerate(row, start=1):
                cell_ref = f"{self._xlsx_column_name(column_number)}{row_number}"
                text = self._xlsx_text(value)
                cells.append(
                    f'<c r="{cell_ref}" t="inlineStr"><is>'
                    f'<t xml:space="preserve">{text}</t>'
                    f'</is></c>'
                )
            xml_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')

        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(xml_rows)}</sheetData>'
            '</worksheet>'
        )

    def _xlsx_column_name(self, column_number):
        name = ""
        while column_number:
            column_number, remainder = divmod(column_number - 1, 26)
            name = chr(65 + remainder) + name
        return name

    def _xlsx_text(self, value):
        text = str(value or "")
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return escape(text)


class InteractionCourseFilter(SimpleListFilter):
    title = 'course'
    parameter_name = 'interaction_course'

    def lookups(self, request, model_admin):
        qs = UserCourse.objects.select_related("course")
        if request.user.groups.filter(name='Teachers').exists():
            qs = qs.filter(course__created_by=request.user)

        course_ids = qs.values_list("course_id", flat=True).distinct()
        courses = Course.objects.filter(id__in=course_ids).order_by("title")
        return [(course.id, course.title) for course in courses]

    def queryset(self, request, queryset):
        if self.value():
            try:
                course_id = int(self.value())
            except (TypeError, ValueError):
                return queryset
            queryset = queryset.filter(course__id=course_id)
        return queryset


class InteractionAgentFilter(SimpleListFilter):
    title = "agent"
    parameter_name = "interaction_agent"

    def lookups(self, request, model_admin):
        qs = UserCourse.objects.select_related("agent", "course")
        if request.user.groups.filter(name="Teachers").exists():
            qs = qs.filter(course__created_by=request.user)

        agent_ids = qs.values_list("agent_id", flat=True).distinct()
        agents = Agent.objects.filter(id__in=agent_ids).order_by("name")
        return [(agent.id, agent.name) for agent in agents]

    def queryset(self, request, queryset):
        if self.value():
            try:
                agent_id = int(self.value())
            except (TypeError, ValueError):
                return queryset
            queryset = queryset.filter(agent__id=agent_id)
        return queryset


class CourseSummaryFilter(SimpleListFilter):
    title = "course"
    parameter_name = "course"

    def lookups(self, request, model_admin):
        qs = Course.objects.all()
        if request.user.groups.filter(name='Teachers').exists() and not request.user.is_superuser:
            qs = qs.filter(created_by=request.user)
        qs = qs.order_by("title")
        return [(str(course.id), course.title) for course in qs]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            return queryset.filter(id=int(value))
        except (TypeError, ValueError):
            return queryset


@admin.register(CourseSummary)
class CourseSummaryAdmin(admin.ModelAdmin):
    change_list_template = 'admin/course_summary_change_list.html'
    list_display = ("title", "canvas_id", "pending_analysis_count_display", "created")
    search_fields = ("title",)
    list_filter = (CourseSummaryFilter, "created")
    ordering = ("-created",)
    analysis_batch_size = 200

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "analyze-interactions/",
                self.admin_site.admin_view(self.analyze_interactions_view),
                name="chatbox_coursesummary_analyze_interactions",
            ),
            path(
                "reset-interactions/",
                self.admin_site.admin_view(self.reset_interactions_view),
                name="chatbox_coursesummary_reset_interactions",
            ),
        ]
        return custom_urls + urls

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.groups.filter(name='Teachers').exists() and not request.user.is_superuser:
            qs = qs.filter(created_by=request.user)
        return qs

    def _visible_courses_queryset(self, request):
        return self.get_queryset(request)

    def _visible_prompts_queryset(self, request, selected_course_id=None):
        qs = Prompt.objects.select_related("course", "course__current_agent", "canvas_user", "agent")
        if request.user.groups.filter(name='Teachers').exists() and not request.user.is_superuser:
            qs = qs.filter(course__created_by=request.user)
        if selected_course_id:
            qs = qs.filter(course_id=selected_course_id)
        return qs

    def _selected_course_id(self, request):
        selected_course_id = request.GET.get("course")
        if selected_course_id:
            return selected_course_id

        first_course = self._visible_courses_queryset(request).order_by("title").first()
        if first_course:
            return str(first_course.id)
        return None

    def analyze_interactions_view(self, request):
        selected_course_id = self._selected_course_id(request)
        redirect_url = reverse("admin:chatbox_coursesummary_changelist")
        if selected_course_id:
            redirect_url = f"{redirect_url}?{urlencode({'course': selected_course_id})}"

        if not self.has_change_permission(request):
            messages.error(request, "No tienes permisos para ejecutar el analisis.")
            return HttpResponseRedirect(redirect_url)

        if request.method != "POST":
            return HttpResponseRedirect(redirect_url)

        pending_ids = list(
            self._visible_prompts_queryset(
                request, selected_course_id=selected_course_id
            )
            .filter(interaction_analyzed_at__isnull=True)
            .order_by("created")
            .values_list("id", flat=True)[: self.analysis_batch_size]
        )

        if not pending_ids:
            messages.info(request, "No hay prompts pendientes de analisis para el filtro actual.")
            return HttpResponseRedirect(redirect_url)

        thread = threading.Thread(
            target=self._run_interaction_analysis_job,
            args=(pending_ids,),
            daemon=True,
        )
        thread.start()

        messages.info(
            request,
            f"Se inició el análisis de {len(pending_ids)} prompts en segundo plano. "
            "Puedes recargar esta vista en unos minutos para ver avances.",
        )
        return HttpResponseRedirect(redirect_url)

    def reset_interactions_view(self, request):
        selected_course_id = self._selected_course_id(request)
        redirect_url = reverse("admin:chatbox_coursesummary_changelist")
        if selected_course_id:
            redirect_url = f"{redirect_url}?{urlencode({'course': selected_course_id})}"

        if not request.user.is_superuser:
            messages.error(request, "Solo un administrador puede resetear análisis.")
            return HttpResponseRedirect(redirect_url)

        if request.method != "POST":
            return HttpResponseRedirect(redirect_url)

        target_qs = self._visible_prompts_queryset(
            request,
            selected_course_id=selected_course_id,
        )
        updated = target_qs.update(
            interaction_type=None,
            answer_correctness=None,
            interaction_analyzed_at=None,
            interaction_analysis_error=None,
        )
        messages.warning(
            request,
            f"Se resetearon {updated} análisis de prompts para el curso seleccionado.",
        )
        return HttpResponseRedirect(redirect_url)

    def _run_interaction_analysis_job(self, prompt_ids):
        close_old_connections()
        for prompt in Prompt.objects.filter(id__in=prompt_ids).order_by("created"):
            analyze_prompt_interaction(prompt)
        close_old_connections()

    def changelist_view(self, request, extra_context=None):
        selected_course_id = self._selected_course_id(request)
        prompt_queryset = self._visible_prompts_queryset(
            request,
            selected_course_id=selected_course_id,
        )
        thirty_days_ago = timezone.now() - timedelta(days=29)
        daily_stats = (
            prompt_queryset.filter(created__gte=thirty_days_ago)
            .annotate(day=TruncDate("created"))
            .values("day")
            .annotate(
                prompt_count=Count("id"),
                distinct_students=Count("canvas_user", distinct=True),
            )
            .order_by("day")
        )
        daily_map = {row["day"]: row for row in daily_stats}
        labels = []
        prompts_per_day = []
        students_per_day = []
        for day_offset in range(30):
            day = (thirty_days_ago + timedelta(days=day_offset)).date()
            labels.append(day.strftime("%d/%m"))
            row = daily_map.get(day)
            prompts_per_day.append(row["prompt_count"] if row else 0)
            students_per_day.append(row["distinct_students"] if row else 0)

        extra_context = extra_context or {}
        extra_context['selected_course'] = selected_course_id
        extra_context['pending_interaction_analysis'] = prompt_queryset.filter(
            interaction_analyzed_at__isnull=True
        ).count()
        extra_context['analyze_interactions_url'] = reverse(
            "admin:chatbox_coursesummary_analyze_interactions"
        )
        extra_context['reset_interactions_url'] = reverse(
            "admin:chatbox_coursesummary_reset_interactions"
        )
        extra_context['can_reset_interactions'] = request.user.is_superuser
        extra_context['courses'] = self._visible_courses_queryset(request).order_by("title")
        extra_context['chart_labels'] = labels
        extra_context['chart_prompts_per_day'] = prompts_per_day
        extra_context['chart_students_per_day'] = students_per_day
        extra_context['total_prompts_last_30_days'] = sum(prompts_per_day)
        extra_context['distinct_students_last_30_days'] = prompt_queryset.filter(
            created__gte=thirty_days_ago
        ).values("canvas_user_id").distinct().count()

        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )
        return response

    @admin.display(description="Pending analysis")
    def pending_analysis_count_display(self, obj):
        return Prompt.objects.filter(
            course=obj,
            interaction_analyzed_at__isnull=True,
        ).count()


class AgentAdminForm(forms.ModelForm):
    instructions = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 22,
                "style": "width:100%;font-family:Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;",
                "placeholder": (
                    "Objetivo del agente\n"
                    "Tono y estilo\n"
                    "Reglas y limites\n"
                    "Formato de respuesta esperado"
                ),
            }
        ),
        help_text=(
            "Define objetivo, tono, restricciones y formato esperado. "
            "Estas instrucciones se aplican a todas las respuestas del agente."
        ),
    )

    class Meta:
        model = Agent
        fields = "__all__"

    def clean_instructions(self):
        instructions = (self.cleaned_data.get("instructions") or "").strip()
        if instructions and len(instructions) < 20:
            raise forms.ValidationError(
                "Las instrucciones son demasiado breves. Agrega mas contexto para guiar al agente."
            )
        return instructions


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    form = AgentAdminForm
    save_on_top = True
    list_display = ("agent_display", "model", "api_key_configured", "test_agent_link", "created_by")
    search_fields = ('name', 'Courses__title', 'model')
    list_filter = ('model',)
    readonly_fields = ("test_agent_link",)
    fieldsets = (
        ("Configuracion", {
            "fields": ("name", "model"),
        }),
        ("Instrucciones del agente", {
            "description": "Esta seccion define el comportamiento pedagogico del agente.",
            "fields": ("instructions",),
        }),
        ("Pruebas", {
            "fields": ("test_agent_link",),
        }),
        ("Integracion", {
            "classes": ("collapse",),
            "fields": ("api_key", "created_by"),
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.groups.filter(name='Teachers').exists():
            qs = qs.filter(created_by=request.user)
        return qs

    @admin.display(description="Name", ordering="name")
    def agent_display(self, obj):
        return obj

    @admin.display(description="API key")
    def api_key_configured(self, obj):
        return bool(obj.api_key)

    @admin.display(description="Probar")
    def test_agent_link(self, obj):
        if not obj or not obj.pk:
            return "Disponible despues de guardar"
        url = reverse("chatgpt", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Abrir chat de prueba</a>', url)
    
    def save_model(self, request, obj, form, change):
        if not obj.created_by: # Only set if it hasnt been set.
             obj.created_by = request.user
        super().save_model(request, obj, form, change)
    

@admin.register(UserCourse)
class UserCourseAdmin(admin.ModelAdmin):
    list_display = ('canvas_user', 'course', 'agent', 'conversation_id')
    search_fields = ('canvas_user__login', 'conversation_id', 'course__title', 'agent__name')
    list_filter = ('course', 'agent')


@admin.register(UserCourseInteractionSummary)
class UserCourseInteractionSummaryAdmin(XlsxExportMixin, admin.ModelAdmin):
    change_list_template = "admin/chatbox/usercourseinteractions/change_list.html"
    list_display = (
        "canvas_user_login",
        "course",
        "agent",
        "view_conversation_link",
        "last_interaction_at_display",
        "analyzed_count_display",
        "pending_count_display",
        "interaction_type_distribution_display",
        "answer_correctness_distribution_display",
        "last_user_message_preview",
        "last_ai_message_preview",
    )
    search_fields = ("canvas_user__login", "course__title")
    list_filter = (InteractionCourseFilter, InteractionAgentFilter)
    readonly_fields = (
        "canvas_user",
        "course",
        "agent",
        "conversation_id",
    )
    list_per_page = 50

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "export-xlsx/",
                self.admin_site.admin_view(self.export_filtered_summary_as_xlsx),
                name="chatbox_usercourseinteractionsummary_export_xlsx",
            ),
        ]
        return custom_urls + urls

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("canvas_user", "course", "agent")
        if request.user.groups.filter(name="Teachers").exists():
            qs = qs.filter(course__created_by=request.user)

        latest_prompt_qs = Prompt.objects.filter(
            course=OuterRef("course"),
            canvas_user=OuterRef("canvas_user"),
            agent=OuterRef("agent"),
        ).order_by("-created")
        first_prompt_qs = Prompt.objects.filter(
            course=OuterRef("course"),
            canvas_user=OuterRef("canvas_user"),
            agent=OuterRef("agent"),
        ).order_by("created")

        prompt_count_qs = (
            Prompt.objects.filter(
                course=OuterRef("course"),
                canvas_user=OuterRef("canvas_user"),
                agent=OuterRef("agent"),
            )
            .values("course", "canvas_user", "agent")
            .annotate(
                total=Count("id"),
                analyzed=Count("id", filter=Q(interaction_analyzed_at__isnull=False)),
                pending=Count("id", filter=Q(interaction_analyzed_at__isnull=True)),
                answer=Count("id", filter=Q(interaction_type=Prompt.InteractionType.ANSWER)),
                clarification=Count(
                    "id",
                    filter=Q(interaction_type=Prompt.InteractionType.CLARIFICATION),
                ),
                question=Count("id", filter=Q(interaction_type=Prompt.InteractionType.QUESTION)),
                out_of_context=Count(
                    "id",
                    filter=Q(interaction_type=Prompt.InteractionType.OUT_OF_CONTEXT),
                ),
                correct=Count(
                    "id",
                    filter=Q(answer_correctness=Prompt.AnswerCorrectness.CORRECT),
                ),
                partially_correct=Count(
                    "id",
                    filter=Q(answer_correctness=Prompt.AnswerCorrectness.PARTIALLY_CORRECT),
                ),
                incorrect=Count(
                    "id",
                    filter=Q(answer_correctness=Prompt.AnswerCorrectness.INCORRECT),
                ),
                not_applicable=Count(
                    "id",
                    filter=Q(answer_correctness=Prompt.AnswerCorrectness.NOT_APPLICABLE),
                ),
            )
        )

        return qs.annotate(
            first_interaction_at=Subquery(
                first_prompt_qs.values("created")[:1],
                output_field=DateTimeField(),
            ),
            last_interaction_at=Subquery(
                latest_prompt_qs.values("created")[:1],
                output_field=DateTimeField(),
            ),
            total_interactions=Coalesce(
                Subquery(prompt_count_qs.values("total")[:1], output_field=IntegerField()),
                Value(0),
            ),
            analyzed_count=Coalesce(
                Subquery(prompt_count_qs.values("analyzed")[:1], output_field=IntegerField()),
                Value(0),
            ),
            pending_count=Coalesce(
                Subquery(prompt_count_qs.values("pending")[:1], output_field=IntegerField()),
                Value(0),
            ),
            answer_count=Coalesce(
                Subquery(prompt_count_qs.values("answer")[:1], output_field=IntegerField()),
                Value(0),
            ),
            clarification_count=Coalesce(
                Subquery(prompt_count_qs.values("clarification")[:1], output_field=IntegerField()),
                Value(0),
            ),
            question_count=Coalesce(
                Subquery(prompt_count_qs.values("question")[:1], output_field=IntegerField()),
                Value(0),
            ),
            out_of_context_count=Coalesce(
                Subquery(prompt_count_qs.values("out_of_context")[:1], output_field=IntegerField()),
                Value(0),
            ),
            correct_count=Coalesce(
                Subquery(prompt_count_qs.values("correct")[:1], output_field=IntegerField()),
                Value(0),
            ),
            partially_correct_count=Coalesce(
                Subquery(prompt_count_qs.values("partially_correct")[:1], output_field=IntegerField()),
                Value(0),
            ),
            incorrect_count=Coalesce(
                Subquery(prompt_count_qs.values("incorrect")[:1], output_field=IntegerField()),
                Value(0),
            ),
            not_applicable_count=Coalesce(
                Subquery(prompt_count_qs.values("not_applicable")[:1], output_field=IntegerField()),
                Value(0),
            ),
            last_user_message=Subquery(
                latest_prompt_qs.values("prompt_text")[:1],
                output_field=TextField(),
            ),
            last_ai_message=Subquery(
                latest_prompt_qs.values("prompt_answer")[:1],
                output_field=TextField(),
            ),
        ).order_by("-last_interaction_at")

    def changelist_view(self, request, extra_context=None):
        querystring = request.GET.urlencode()
        export_url = reverse(
            "admin:chatbox_usercourseinteractionsummary_export_xlsx"
        )
        if querystring:
            export_url = f"{export_url}?{querystring}"

        extra_context = extra_context or {}
        extra_context["export_xlsx_url"] = export_url
        return super().changelist_view(request, extra_context=extra_context)

    def _filtered_changelist_queryset(self, request):
        changelist = self.get_changelist_instance(request)
        return changelist.queryset

    def _summary_export_headers(self):
        return [
            "student",
            "course",
            "agent_id",
            "agent_name",
            "first_interaction_at",
            "last_interaction_at",
            "total_interactions",
            "interactions_during_class",
            "interactions_outside_class",
            *[
                f"interaction_type_{value}"
                for value, _label in Prompt.InteractionType.choices
            ],
            *[
                f"answer_correctness_{value}"
                for value, _label in Prompt.AnswerCorrectness.choices
            ],
        ]

    def _summary_export_rows(self, queryset):
        rows = list(queryset.select_related("canvas_user", "course", "agent"))
        session_counts = self._interaction_session_counts(rows)
        for row in rows:
            key = (row.course_id, row.canvas_user_id, row.agent_id)
            counts = session_counts.get(key, {"during": 0, "outside": 0})
            yield [
                row.canvas_user.login if row.canvas_user else "",
                row.course.title if row.course else "",
                row.agent_id or "",
                row.agent.name if row.agent else "",
                self._format_datetime(row.first_interaction_at),
                self._format_datetime(row.last_interaction_at),
                row.total_interactions,
                counts["during"],
                counts["outside"],
                row.answer_count,
                row.clarification_count,
                row.question_count,
                row.out_of_context_count,
                row.correct_count,
                row.partially_correct_count,
                row.incorrect_count,
                row.not_applicable_count,
            ]

    def _interaction_session_counts(self, rows):
        keys = {
            (row.course_id, row.canvas_user_id, row.agent_id)
            for row in rows
            if row.course_id and row.canvas_user_id
        }
        if not keys:
            return {}

        course_ids = {course_id for course_id, _user_id, _agent_id in keys}
        user_ids = {user_id for _course_id, user_id, _agent_id in keys}
        agent_ids = {
            agent_id for _course_id, _user_id, agent_id in keys if agent_id is not None
        }
        include_null_agent = any(agent_id is None for _course_id, _user_id, agent_id in keys)

        schedules_by_course = defaultdict(list)
        for schedule in CourseClassSchedule.objects.filter(course_id__in=course_ids):
            schedules_by_course[schedule.course_id].append(schedule)

        prompt_filter = Q(course_id__in=course_ids, canvas_user_id__in=user_ids)
        if agent_ids and include_null_agent:
            prompt_filter &= Q(agent_id__in=agent_ids) | Q(agent_id__isnull=True)
        elif agent_ids:
            prompt_filter &= Q(agent_id__in=agent_ids)
        else:
            prompt_filter &= Q(agent_id__isnull=True)

        counts = defaultdict(lambda: {"during": 0, "outside": 0})
        prompts = (
            Prompt.objects.filter(prompt_filter)
            .only("course_id", "canvas_user_id", "agent_id", "created")
            .order_by()
        )
        for prompt in prompts.iterator():
            key = (prompt.course_id, prompt.canvas_user_id, prompt.agent_id)
            if key not in keys:
                continue

            bucket = "during" if self._prompt_is_during_class(prompt, schedules_by_course) else "outside"
            counts[key][bucket] += 1

        return counts

    def _prompt_is_during_class(self, prompt, schedules_by_course):
        created = timezone.localtime(prompt.created, LOCAL_TIME_ZONE)
        created_date = created.date()
        created_time = created.time()
        for schedule in schedules_by_course.get(prompt.course_id, []):
            if schedule.weekday != created.weekday():
                continue
            if schedule.active_from and schedule.active_from > created_date:
                continue
            if schedule.active_until and schedule.active_until < created_date:
                continue
            if schedule.start_time <= schedule.end_time:
                if schedule.start_time <= created_time <= schedule.end_time:
                    return True
            elif created_time >= schedule.start_time or created_time <= schedule.end_time:
                return True
        return False

    def _summary_export_filename(self):
        timestamp = timezone.localtime(timezone.now()).strftime("%Y%m%d-%H%M%S")
        return f"student-interactions-summary-{timestamp}.xlsx"

    def export_filtered_summary_as_xlsx(self, request):
        if not self.has_view_or_change_permission(request):
            messages.error(request, "No tienes permisos para exportar interacciones.")
            return HttpResponseRedirect(
                reverse("admin:chatbox_usercourseinteractionsummary_changelist")
            )

        rows = [
            self._summary_export_headers(),
            *self._summary_export_rows(self._filtered_changelist_queryset(request)),
        ]
        workbook = self._build_xlsx(rows, sheet_name="Student interactions")
        response = HttpResponse(
            workbook.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{self._summary_export_filename()}"'
        )
        return response

    @admin.display(description="Student login", ordering="canvas_user__login")
    def canvas_user_login(self, obj):
        return obj.canvas_user.login

    @admin.display(description="Conversation")
    def view_conversation_link(self, obj):
        url = reverse(
            "teacher_student_chat_detail",
            args=[obj.course_id, obj.canvas_user_id],
        )
        if obj.agent_id:
            url = f"{url}?{urlencode({'agent': obj.agent_id})}"
        return format_html('<a href="{}" target="_blank">Ver conversación</a>', url)

    @admin.display(description="Last interaction", ordering="last_interaction_at")
    def last_interaction_at_display(self, obj):
        return obj.last_interaction_at

    @admin.display(description="Analyzed", ordering="analyzed_count")
    def analyzed_count_display(self, obj):
        return obj.analyzed_count

    @admin.display(description="Pending", ordering="pending_count")
    def pending_count_display(self, obj):
        return obj.pending_count

    @admin.display(description="Interaction type", ordering="analyzed_count")
    def interaction_type_distribution_display(self, obj):
        answer = int(obj.answer_count or 0)
        clarification = int(obj.clarification_count or 0)
        question = int(obj.question_count or 0)
        out_of_context = int(obj.out_of_context_count or 0)
        total = answer + clarification + question + out_of_context
        if total == 0:
            return "Sin análisis"

        answer_pct = (answer * 100) / total
        clarification_pct = (clarification * 100) / total
        question_pct = (question * 100) / total
        out_pct = (out_of_context * 100) / total
        title = (
            f"answer: {answer} | clarification: {clarification} | "
            f"question: {question} | out_of_context: {out_of_context}"
        )

        answer_pct_str = f"{answer_pct:.2f}"
        clarification_pct_str = f"{clarification_pct:.2f}"
        question_pct_str = f"{question_pct:.2f}"
        out_pct_str = f"{out_pct:.2f}"

        return format_html(
            (
                '<div title="{}" style="display:flex;width:170px;height:14px;border-radius:7px;'
                'overflow:hidden;border:1px solid #d9d9d9;background:#f4f4f4;">'
                '<span title="answer: {}" style="width:{}%;background:#4c78a8;"></span>'
                '<span title="clarification: {}" style="width:{}%;background:#f2cf5b;"></span>'
                '<span title="question: {}" style="width:{}%;background:#59a14f;"></span>'
                '<span title="out_of_context: {}" style="width:{}%;background:#e15759;"></span>'
                "</div>"
            ),
            title,
            answer,
            answer_pct_str,
            clarification,
            clarification_pct_str,
            question,
            question_pct_str,
            out_of_context,
            out_pct_str,
        )

    @admin.display(description="Answer correctness", ordering="answer_count")
    def answer_correctness_distribution_display(self, obj):
        total_answers = int(obj.answer_count or 0)
        correct = int(obj.correct_count or 0)
        partially = int(obj.partially_correct_count or 0)
        incorrect = int(obj.incorrect_count or 0)
        if total_answers == 0:
            return "Sin respuestas tipo answer"

        correct_pct = (correct * 100) / total_answers
        partially_pct = (partially * 100) / total_answers
        incorrect_pct = (incorrect * 100) / total_answers

        correct_pct_str = f"{correct_pct:.2f}"
        partially_pct_str = f"{partially_pct:.2f}"
        incorrect_pct_str = f"{incorrect_pct:.2f}"

        title = (
            f"answers evaluadas: {total_answers} | "
            f"correct: {correct} | partially_correct: {partially} | incorrect: {incorrect}"
        )
        return format_html(
            (
                '<div title="{}" style="display:flex;width:170px;height:14px;border-radius:7px;'
                'overflow:hidden;border:1px solid #d9d9d9;background:#f4f4f4;">'
                '<span title="correct: {}" style="width:{}%;background:#59a14f;"></span>'
                '<span title="partially_correct: {}" style="width:{}%;background:#f2cf5b;"></span>'
                '<span title="incorrect: {}" style="width:{}%;background:#e15759;"></span>'
                "</div>"
            ),
            title,
            correct,
            correct_pct_str,
            partially,
            partially_pct_str,
            incorrect,
            incorrect_pct_str,
        )

    @admin.display(description="Last prompt", ordering="last_user_message")
    def last_user_message_preview(self, obj):
        text = (obj.last_user_message or "").strip()
        return text[:200] + ("..." if len(text) > 200 else "")

    @admin.display(description="Last AI response", ordering="last_ai_message")
    def last_ai_message_preview(self, obj):
        text = (obj.last_ai_message or "").strip()
        return text[:200] + ("..." if len(text) > 200 else "")

from django.contrib import admin
from django.urls import path
from studio import views  # views.py is inside studio app

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('upload/', views.upload_dataset, name='upload_dataset'),
    path('full_dataset/', views.full_dataset, name='full_dataset'),
    path('run_query/<str:dataset_name>/', views.run_query, name='run_query'),
    path('preview/<str:dataset_name>/', views.dataset_preview, name='dataset_preview'),
    path('generate_chart/', views.generate_chart, name='generate_chart'),
    path('chart_builder/', views.chart_builder, name='chart_builder'),
    path("report-builder/", views.report_builder, name="report_builder"),
    path('auto_visualize/', views.auto_visualize_dataset, name='auto_visualize'),
    path('save_report_blocks/', views.save_report_blocks, name='save_report_blocks'),
    path('save_report/<str:format>/', views.save_report, name='save_report'),
    path('get_available_charts/', views.get_available_charts, name='get_available_charts'),
    path('clear_session/', views.clear_session_data_endpoint, name='clear_session'),
]
from django.contrib import admin
from django.urls import path
from studio import views  # views.py is inside studio app

urlpatterns = [
    # Admin URL is defined in core/urls.py - removed duplicate
    path('', views.index, name='index'),
    path('upload/', views.upload_dataset, name='upload_dataset'),
    path('upload_datasets/', views.upload_multiple_datasets, name='upload_multiple_datasets'),
    path('search_online_datasets/', views.search_online_datasets, name='search_online_datasets'),
    path('fetch_online_dataset/', views.fetch_online_dataset, name='fetch_online_dataset'),
    path('datasets/', views.multi_dataset_preview, name='multi_dataset_preview'),
    path('switch_dataset/<int:dataset_index>/', views.switch_dataset, name='switch_dataset'),
    path('merge_datasets/', views.merge_datasets, name='merge_datasets'),
    path('remove_dataset/<int:dataset_index>/', views.remove_dataset, name='remove_dataset'),
    path('run_multi_query/', views.run_multi_dataset_query, name='run_multi_query'),
    path('full_dataset/', views.full_dataset, name='full_dataset'),
    path('run_query/<str:dataset_name>/', views.run_query, name='run_query'),
    # Legacy dataset_preview URL removed - use multi_dataset_preview instead
    path('generate_chart/', views.generate_chart, name='generate_chart'),
    path('chart_builder/', views.chart_builder, name='chart_builder'),
    path("report-builder/", views.report_builder, name="report_builder"),
    path('auto_visualize/', views.auto_visualize_dataset, name='auto_visualize'),
    path('save_report_blocks/', views.save_report_blocks, name='save_report_blocks'),
    path('save_report/<str:format>/', views.save_report, name='save_report'),
    path('get_available_charts/', views.get_available_charts, name='get_available_charts'),
    path('get_chat_history/', views.get_chat_history, name='get_chat_history'),
    path('clear_session/', views.clear_session_data_endpoint, name='clear_session'),
    path('session_cleanup/', views.session_cleanup_endpoint, name='session_cleanup'),
    path('session_end/', views.session_end_cleanup, name='session_end'),
    path('advanced_viz/', views.advanced_visualization_builder, name='advanced_viz'),
    path('advanced_viz/<str:dataset_name>/', views.advanced_visualization_builder, name='advanced_viz_with_dataset'),
    path('debug_session/', views.debug_session, name='debug_session'),
    path('generate_advanced_chart/', views.generate_advanced_chart, name='generate_advanced_chart'),
    path('get_column_values/', views.get_column_values, name='get_column_values'),
    path('transcribe_audio/', views.transcribe_audio, name='transcribe_audio'),
]
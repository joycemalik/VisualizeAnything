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
    path('auto_visualize/', views.auto_visualize_dataset, name='auto_visualize'),
]

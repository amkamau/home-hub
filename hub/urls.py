from django.urls import path
from . import views

urlpatterns = [
    path("", views.movies, name="movies"),
    path("movies/", views.movies, name="movies"),
    path("movies/play/<path:relative_path>/", views.play_video, name="play_video"),
    path("movies/playlist/", views.playlist, name="playlist"),
    path("files/", views.files_home, name="files_home"),
    path("files/download/<path:relative_path>/", views.download_file, name="download_file"),
    path("files/action/", views.file_action, name="file_action"),
]

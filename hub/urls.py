from django.urls import path
from . import views

urlpatterns = [
    # path("", views.media, name="media"),
    # path("home/", views.home, name="home"),
    path("", views.home, name="home"),
    path("media/", views.media, name="media"),
    path("media/play/<path:relative_path>/", views.play_video, name="play_video"),
    path("media/playlist/", views.playlist, name="playlist"),
    path("files/", views.files_home, name="files_home"),
    path("files/download/<path:relative_path>/", views.download_file, name="download_file"),
    path("files/action/", views.file_action, name="file_action"),
]

# encoding: utf-8

from ckantoolkit import BaseController

from .views import resource_download, filesystem_resource_download, uploaded_file_redirect


class S3Controller(BaseController):

    def resource_download(self, id, resource_id, filename=None):
        return resource_download('dataset', id, resource_id, filename)

    def filesystem_resource_download(self, id, resource_id, filename=None):
        return filesystem_resource_download('dataset', id, resource_id, filename)

    def uploaded_file_redirect(self, upload_to, filename):
        return uploaded_file_redirect(upload_to, filename)

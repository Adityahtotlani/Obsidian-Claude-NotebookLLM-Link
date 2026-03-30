import os
import pickle
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/drive.file']


class DriveUploader:
    def __init__(self, credentials_file: str, token_file: str = None):
        self.credentials_file = credentials_file
        self.token_file = token_file or str(Path.home() / '.obsidian-bridge-token.pickle')
        self.service = None

    def authenticate(self):
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.token_file, 'wb') as f:
                pickle.dump(creds, f)

        self.service = build('drive', 'v3', credentials=creds)

    def get_or_create_folder(self, name: str) -> str:
        q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(q=q, fields="files(id)").execute()
        files = results.get('files', [])
        if files:
            return files[0]['id']
        meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
        folder = self.service.files().create(body=meta, fields='id').execute()
        return folder['id']

    def upload_file(self, file_path: Path, folder_id: str) -> str:
        from googleapiclient.http import MediaFileUpload
        meta = {'name': file_path.name, 'parents': [folder_id]}
        media = MediaFileUpload(str(file_path), mimetype='text/markdown', resumable=True)
        f = self.service.files().create(body=meta, media_body=media, fields='id,webViewLink').execute()
        # Make readable by anyone with link so NotebookLM can use it
        self.service.permissions().create(
            fileId=f['id'],
            body={'type': 'anyone', 'role': 'reader'},
        ).execute()
        return f.get('webViewLink', '')

    def upload_bundle(self, files: list, folder_name: str = "ObsidianNotebookLM") -> list:
        if not self.service:
            self.authenticate()
        folder_id = self.get_or_create_folder(folder_name)
        return [self.upload_file(f, folder_id) for f in files]

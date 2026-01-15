"""
LinkedIn JD Analyzer - Gmail OAuth 2.0 Authentication Module

Google Cloud Console에서 OAuth 2.0 설정 후 사용:
1. https://console.cloud.google.com/ 에서 프로젝트 생성
2. Gmail API 활성화
3. OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱)
4. credentials.json 다운로드하여 config/ 폴더에 저장

Usage:
    python -m notifier.gmail_oauth --setup    # 최초 인증 설정
    python -m notifier.gmail_oauth --test     # 인증 테스트
"""

import os
import pickle
import logging
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BASE_DIR, DATA_DIR

logger = logging.getLogger(__name__)

# Gmail API 권한 범위
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# 인증 파일 경로
CREDENTIALS_FILE = BASE_DIR / "config" / "credentials.json"
TOKEN_FILE = DATA_DIR / "gmail_token.pickle"


class GmailOAuth:
    """
    Gmail OAuth 2.0 인증 관리 클래스

    최초 실행 시 브라우저에서 Google 계정 로그인 필요
    이후 토큰이 자동으로 갱신됨
    """

    def __init__(
        self,
        credentials_file: Path = None,
        token_file: Path = None
    ):
        """
        Args:
            credentials_file: Google Cloud에서 다운로드한 credentials.json 경로
            token_file: 저장된 토큰 파일 경로
        """
        self.credentials_file = credentials_file or CREDENTIALS_FILE
        self.token_file = token_file or TOKEN_FILE
        self.creds: Optional[Credentials] = None
        self.service = None

    def authenticate(self) -> Credentials:
        """
        Gmail API 인증 수행

        1. 저장된 토큰이 있으면 로드
        2. 토큰이 만료되었으면 갱신
        3. 토큰이 없으면 브라우저에서 인증 진행

        Returns:
            Google API Credentials 객체
        """
        # 저장된 토큰 확인
        if self.token_file.exists():
            logger.info("Loading saved token...")
            with open(self.token_file, 'rb') as token:
                self.creds = pickle.load(token)

        # 토큰이 없거나 유효하지 않은 경우
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                # 토큰 갱신
                logger.info("Refreshing expired token...")
                self.creds.refresh(Request())
            else:
                # 새로운 인증 진행
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {self.credentials_file}\n"
                        "Please download it from Google Cloud Console:\n"
                        "1. Go to https://console.cloud.google.com/\n"
                        "2. Create a project and enable Gmail API\n"
                        "3. Create OAuth 2.0 Client ID (Desktop app)\n"
                        "4. Download credentials.json to config/ folder"
                    )

                logger.info("Starting OAuth flow (browser will open)...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file),
                    SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            # 토큰 저장
            self._save_token()

        logger.info("Gmail OAuth authentication successful")
        return self.creds

    def _save_token(self):
        """토큰을 파일로 저장"""
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.token_file, 'wb') as token:
            pickle.dump(self.creds, token)
        logger.info(f"Token saved to {self.token_file}")

    def get_service(self):
        """
        Gmail API 서비스 객체 반환

        Returns:
            Gmail API service 객체
        """
        if not self.creds:
            self.authenticate()

        if not self.service:
            self.service = build('gmail', 'v1', credentials=self.creds)

        return self.service

    def revoke_token(self) -> bool:
        """
        토큰 폐기 (재인증 필요하게 됨)

        Returns:
            성공 여부
        """
        if self.token_file.exists():
            self.token_file.unlink()
            logger.info("Token revoked successfully")
            return True
        return False

    def test_connection(self) -> dict:
        """
        Gmail API 연결 테스트

        Returns:
            사용자 프로필 정보
        """
        try:
            service = self.get_service()
            profile = service.users().getProfile(userId='me').execute()
            logger.info(f"Connected as: {profile.get('emailAddress')}")
            return {
                "success": True,
                "email": profile.get('emailAddress'),
                "messages_total": profile.get('messagesTotal'),
                "threads_total": profile.get('threadsTotal')
            }
        except HttpError as e:
            logger.error(f"Gmail API error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return {"success": False, "error": str(e)}


def setup_oauth():
    """최초 OAuth 설정 진행"""
    print("=" * 60)
    print("Gmail OAuth 2.0 Setup")
    print("=" * 60)

    oauth = GmailOAuth()

    # credentials.json 확인
    if not CREDENTIALS_FILE.exists():
        print(f"\n❌ credentials.json not found at:")
        print(f"   {CREDENTIALS_FILE}")
        print("\n📋 Setup Instructions:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project (or select existing)")
        print("3. Enable Gmail API:")
        print("   - Go to 'APIs & Services' > 'Library'")
        print("   - Search for 'Gmail API' and enable it")
        print("4. Create OAuth 2.0 credentials:")
        print("   - Go to 'APIs & Services' > 'Credentials'")
        print("   - Click 'Create Credentials' > 'OAuth client ID'")
        print("   - Choose 'Desktop app' as application type")
        print("   - Download the JSON file")
        print(f"5. Rename to 'credentials.json' and place in:")
        print(f"   {CREDENTIALS_FILE.parent}")
        return False

    print(f"\n✅ credentials.json found at {CREDENTIALS_FILE}")
    print("\n🔐 Starting OAuth authentication...")
    print("   (A browser window will open for Google login)")

    try:
        oauth.authenticate()
        result = oauth.test_connection()

        if result["success"]:
            print(f"\n✅ Authentication successful!")
            print(f"   Email: {result['email']}")
            print(f"   Token saved to: {TOKEN_FILE}")
            return True
        else:
            print(f"\n❌ Connection test failed: {result['error']}")
            return False

    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        return False


def test_oauth():
    """OAuth 연결 테스트"""
    print("=" * 60)
    print("Gmail OAuth Connection Test")
    print("=" * 60)

    oauth = GmailOAuth()

    if not TOKEN_FILE.exists():
        print("\n❌ No token found. Run setup first:")
        print("   python -m notifier.gmail_oauth --setup")
        return False

    result = oauth.test_connection()

    if result["success"]:
        print(f"\n✅ Connection successful!")
        print(f"   Email: {result['email']}")
        print(f"   Total messages: {result.get('messages_total', 'N/A')}")
        return True
    else:
        print(f"\n❌ Connection failed: {result['error']}")
        return False


def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Gmail OAuth 2.0 Setup and Test"
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run initial OAuth setup"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test OAuth connection"
    )
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Revoke saved token"
    )

    args = parser.parse_args()

    if args.setup:
        setup_oauth()
    elif args.test:
        test_oauth()
    elif args.revoke:
        oauth = GmailOAuth()
        if oauth.revoke_token():
            print("✅ Token revoked. Run --setup to re-authenticate.")
        else:
            print("❌ No token found to revoke.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

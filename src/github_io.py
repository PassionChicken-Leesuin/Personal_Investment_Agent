"""GitHub Contents API 로 파일을 커밋한다.

Streamlit Cloud 의 파일시스템은 임시(ephemeral)라, 앱에서 편집한 내용을
영속화하려면 GitHub 저장소로 직접 커밋해야 한다. 이 모듈이 그 역할을 담당.

토큰은 절대 코드/저장소에 넣지 말 것 → Streamlit Secrets 또는 환경변수로 주입.
"""
import base64
import requests

API_ROOT = "https://api.github.com"
TIMEOUT = 20


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "stock-agent-dashboard",
    }


def get_file_sha(token: str, repo: str, path: str, branch: str) -> str | None:
    """현재 파일의 blob SHA. 파일이 없으면 None (신규 생성)."""
    url = f"{API_ROOT}/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=TIMEOUT)
    if r.status_code == 200:
        return r.json().get("sha")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return None


def commit_text_file(
    token: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
) -> dict:
    """텍스트 파일 하나를 생성/갱신 커밋. 성공 시 응답 JSON 반환, 실패 시 예외."""
    sha = get_file_sha(token, repo, path, branch)
    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha  # 기존 파일 갱신 시 필수
    url = f"{API_ROOT}/repos/{repo}/contents/{path}"
    r = requests.put(url, headers=_headers(token), json=body, timeout=TIMEOUT)
    if not r.ok:
        # GitHub 오류 메시지를 그대로 노출해 디버깅 쉽게
        raise RuntimeError(f"GitHub {r.status_code}: {r.json().get('message', r.text)}")
    return r.json()

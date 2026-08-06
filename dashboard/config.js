// CareFlow 프론트엔드 설정
// 현재 위치가 localhost면 로컬 서버 사용, 아니면 API Gateway 사용
const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE = IS_LOCAL ? '' : 'https://zwcm8nfy79.execute-api.us-east-1.amazonaws.com';

// 로그인 후 받은 토큰을 저장/관리하는 유틸리티
const Auth = {
  getToken() {
    return localStorage.getItem('careflow_token');
  },
  setToken(token) {
    localStorage.setItem('careflow_token', token);
  },
  getUser() {
    const data = localStorage.getItem('careflow_user');
    return data ? JSON.parse(data) : null;
  },
  setUser(user) {
    localStorage.setItem('careflow_user', JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem('careflow_token');
    localStorage.removeItem('careflow_user');
  },
  isLoggedIn() {
    return !!this.getToken();
  }
};

// API 호출 헬퍼 — 인증 헤더 자동 포함
async function apiFetch(path, options = {}) {
  const url = API_BASE + path;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  const token = Auth.getToken();
  if (token) {
    headers['Authorization'] = 'Bearer ' + token;
  }
  const res = await fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  });
  return res;
}

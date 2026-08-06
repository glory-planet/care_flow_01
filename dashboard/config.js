// CareFlow 프론트엔드 설정
// API Gateway 엔드포인트 (Lambda 백엔드)
const API_BASE = 'https://zwcm8nfy79.execute-api.us-east-1.amazonaws.com/prod';

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

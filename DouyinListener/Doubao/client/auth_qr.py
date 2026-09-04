#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音 Web 端二维码登录 + 二次验证（短信/邮箱）
参考 danmu-server 项目实现 (sso.douyin.com 流程)

流程：
1. GET /passport/web/get_qrcode/?aid=6383&device_id=xxx&service=https://www.douyin.com
   -> { token, qrcode_index_url, qrcode }
2. 轮询 POST /passport/web/check_qrconnect/ (token)
   -> status: 1=未扫码 / 2=已扫码待确认 / 3=已确认 / 5=已过期
      如果需要二次验证 -> redirect_url 含 need_sms_verify=1 或 need_email_verify=1
3. 二次验证：POST /passport/web/.../ 发送验证码 -> POST 校验 -> 拿到 cookies
4. 最终 cookies: sessionid / sessionid_ss / passport_csrf_token / uid_tt / uid_tt_ss / sid_tt / tt_token 等
"""
import asyncio, json, re, time, random, secrets, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Callable, Awaitable
from urllib.parse import urlencode, quote, urlparse, parse_qs

try:
    import aiohttp
except ImportError:
    aiohttp = None

# ---------- 常量 ----------
DEFAULT_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
    'Referer': 'https://www.douyin.com/',
    'Origin': 'https://www.douyin.com',
}

PASSPORT_HOST = 'https://sso.douyin.com'
LIVE_HOST = 'https://live.douyin.com'

QRCODE_URL = PASSPORT_HOST + '/passport/web/get_qrcode/'
CHECK_URL = PASSPORT_HOST + '/passport/web/check_qrconnect/'
SEND_SMS_URL = PASSPORT_HOST + '/passport/web/send_sms_code/'
SMS_LOGIN_URL = PASSPORT_HOST + '/passport/web/login_sms/'
SAVE_COOKIES_TO = Path(__file__).resolve().parent / 'cookies.json'
DANMU_SERVER_COOKIE_FILE = (
    Path.home() / 'AppData' / 'Roaming' / 'obsplus' / 'app' / 'danmu-server'
    / 'browser_cache' / 'Webview2Cache' / 'WebviewCookies.dat'
)


def _gen_device_id() -> str:
    # 设备ID：固定为 19 位数字（danmu-server 用此格式）
    return str(random.randint(7000000000000000000, 7999999999999999999))


def _gen_fp() -> str:
    return ''.join(random.choice('0123456789abcdef') for _ in range(16))


class QrLogin:
    """抖音二维码登录会话"""

    def __init__(self, proxy: Optional[str] = None, cookie_file: Optional[Path] = None):
        if aiohttp is None:
            raise RuntimeError('请先安装 aiohttp: pip install aiohttp')
        self.proxy = proxy
        self.cookie_file = cookie_file or SAVE_COOKIES_TO
        self._session: Optional[aiohttp.ClientSession] = None
        self.device_id = _gen_device_id()
        self.fp = _gen_fp()
        self.token: Optional[str] = None
        self.qr_url: Optional[str] = None  # 二维码扫码链接 https://...qrcode
        self.qr_img: Optional[str] = None  # base64 图片 data url
        self._last_check_redirect: Optional[str] = None
        self._cookies: Dict[str, str] = {}
        self._verify_state: dict = {}  # 二次验证上下文（手机号/邮箱遮罩/ticket等）
        self.on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self._session = aiohttp.ClientSession(timeout=timeout, headers=DEFAULT_HEADERS)
        # 首次访问主页拿基础 cookies
        try:
            async with self._session.get('https://www.douyin.com/', proxy=self.proxy) as r:
                await r.text()
        except Exception:
            pass
        return self

    async def __aexit__(self, *a):
        if self._session:
            await self._session.close()
            self._session = None

    # ---------- 基础请求 ----------
    def _common_params(self) -> dict:
        return {
            'aid': '6383',
            'device_id': self.device_id,
            'fp': self.fp,
            'account_sdk_source': 'sso',
            'sdk_version': '2.2.1-beta.6',
            'language': 'zh',
            'web_timestamp': str(int(time.time())),
        }

    async def _get(self, url: str, params: dict = None) -> dict:
        p = self._common_params()
        if params:
            p.update(params)
        async with self._session.get(url, params=p, proxy=self.proxy) as r:
            txt = await r.text()
            try:
                return json.loads(txt)
            except Exception:
                return {'raw': txt[:500], 'status_code': r.status}

    async def _post(self, url: str, data: dict = None) -> dict:
        p = self._common_params()
        # 带上已有的 csrf token
        cookies = self._session.cookie_jar.filter_cookies(url)
        csrf = cookies.get('passport_csrf_token')
        if csrf:
            p['csrf_token'] = csrf.value
        form = aiohttp.FormData()
        if data:
            for k, v in data.items():
                form.add_field(k, str(v))
        async with self._session.post(url, params=p, data=form, proxy=self.proxy) as r:
            txt = await r.text()
            try:
                return json.loads(txt)
            except Exception:
                return {'raw': txt[:500], 'status_code': r.status}

    # ---------- 二维码 ----------
    async def fetch_qrcode(self) -> dict:
        """获取二维码。返回 {token, qr_url, qr_img}"""
        data = await self._get(QRCODE_URL, {
            'service': 'https://www.douyin.com',
            'biz_params': json.dumps({'aid': 6383, 'type': 0}, separators=(',', ':')),
            'need_qr_img': '1',
        })
        # data 典型结构:
        # { error_id:..., data:{ token, qrcode:"https://sso.douyin.com/qrcode?...token=xxx",
        #                          qrcode_index_url, qr_image:"data:image/png;base64,..." } }
        d = data.get('data') or {}
        if not d:
            raise RuntimeError(f'获取二维码失败: {data}')
        self.token = d.get('token') or ''
        self.qr_url = d.get('qrcode') or d.get('qrcode_index_url') or ''
        self.qr_img = d.get('qr_image') or ''
        # 把 qr_img 做成 data url
        if self.qr_img and not self.qr_img.startswith('data:'):
            self.qr_img = 'data:image/png;base64,' + self.qr_img
        return {'token': self.token, 'qr_url': self.qr_url, 'qr_img': self.qr_img}

    async def check_scan(self) -> dict:
        """
        轮询扫码状态。返回：
        { status, extra:{}, redirect_url?, need_verify?, verify_info? }
        status:
            - 'waiting' 未扫码 (code in 1, 1013)
            - 'scanned' 已扫码待确认 (code 2)
            - 'confirmed' 已确认，已拿到 cookies (code 3)
            - 'expired' 过期 (code 5, 1022)
            - 'need_sms_verify' / 'need_email_verify' 二次验证
        """
        if not self.token:
            raise RuntimeError('请先获取二维码')
        data = await self._post(CHECK_URL, {
            'token': self.token,
            'service': 'https://www.douyin.com',
            'biz_params': json.dumps({'aid': 6383, 'type': 0}, separators=(',', ':')),
        })
        # danmu-server 兼容字段
        d = data.get('data') or {}
        status = d.get('status') or data.get('status')
        err_tips = d.get('err_tip') or d.get('error_tips') or ''
        redirect = d.get('redirect_url') or d.get('redirect') or ''
        extra = d.get('extra') or {}

        code = data.get('error_code', 0) or data.get('code', 0)
        status_map = {
            1: 'waiting', 2: 'scanned', 3: 'confirmed', 4: 'confirmed',
            5: 'expired', 1013: 'waiting', 1022: 'expired',
            1025: 'refreshed',
        }
        st = status_map.get(code, None)

        # 判断二次验证
        need_sms = 'need_sms_verify' in redirect or extra.get('sms_tip')
        need_email = 'need_email_verify' in redirect or extra.get('email_tip')

        if need_sms:
            st = 'need_sms_verify'
            self._last_check_redirect = redirect
            self._verify_state = self._parse_verify(extra, redirect, 'sms')
        elif need_email:
            st = 'need_email_verify'
            self._last_check_redirect = redirect
            self._verify_state = self._parse_verify(extra, redirect, 'email')
        elif st is None:
            # 兼容字段
            if status in (1, 2, 3, 5):
                st = status_map.get(status, 'waiting')
            else:
                st = 'waiting'

        if st == 'confirmed':
            # 请求 redirect_url 把 set-cookie 带上
            if redirect:
                try:
                    async with self._session.get(redirect, allow_redirects=True, proxy=self.proxy) as rr:
                        await rr.text()
                except Exception:
                    pass
            # 再请求一次首页确保 cookies 落地
            try:
                async with self._session.get('https://www.douyin.com/', proxy=self.proxy) as rr:
                    await rr.text()
            except Exception:
                pass
            self._collect_cookies()

        return {'status': st, 'error_tips': err_tips, 'verify_info': self._verify_state if st.startswith('need_') else None}

    def _parse_verify(self, extra: dict, redirect: str, mode: str) -> dict:
        """从 check 响应里提取二次验证需要的字段"""
        info = {'mode': mode}
        # 手机号/邮箱遮罩
        if mode == 'sms':
            info['mask'] = extra.get('mobile') or extra.get('sms_tip') or ''
            info['mobile'] = extra.get('mobile') or ''
            info['country_code'] = extra.get('country_code') or '+86'
        else:
            info['mask'] = extra.get('email') or extra.get('email_tip') or ''
            info['email'] = extra.get('email') or ''
        # ticket / challenge
        q = parse_qs(urlparse(redirect).query)
        info['ticket'] = (q.get('ticket') or [''])[0]
        info['challenge'] = (q.get('challenge') or q.get('verify_challenge') or [''])[0]
        info['original'] = (q.get('original') or q.get('verify_type') or [''])[0]
        info['uid'] = (q.get('uid') or [''])[0]
        # extra 中可能有 mobile_str
        for k in ('ticket', 'mobile_str', 'mobile', 'country_code', 'verify_type', 'aid'):
            if k in extra:
                info[k] = extra[k]
        return info

    # ---------- 二次验证 ----------
    async def send_verify_code(self) -> dict:
        """发送验证码（短信/邮箱）"""
        vs = self._verify_state
        if not vs:
            raise RuntimeError('当前无需二次验证')
        mode = vs.get('mode', 'sms')
        data = {
            'ticket': vs.get('ticket') or '',
            'mobile': vs.get('mobile') or vs.get('mobile_str') or '',
            'country_code': vs.get('country_code') or '+86',
            'verify_type': mode,
        }
        # danmu-server 发送短信 code 的 URL
        url = SEND_SMS_URL if mode == 'sms' else (PASSPORT_HOST + '/passport/web/send_email_code/')
        res = await self._post(url, data)
        return res

    async def commit_verify_code(self, code: str) -> dict:
        """提交验证码"""
        vs = self._verify_state
        mode = vs.get('mode', 'sms')
        data = {
            'code': code,
            'ticket': vs.get('ticket') or '',
            'mobile': vs.get('mobile') or vs.get('mobile_str') or '',
            'country_code': vs.get('country_code') or '+86',
            'verify_type': mode,
            'service': 'https://www.douyin.com',
        }
        res = await self._post(SMS_LOGIN_URL, data)
        # 成功后 data.redirect_url -> 请求即可落地 cookies
        d = res.get('data') or {}
        redirect = d.get('redirect_url') or d.get('redirect') or ''
        if redirect:
            try:
                async with self._session.get(redirect, allow_redirects=True, proxy=self.proxy) as rr:
                    await rr.text()
            except Exception:
                pass
            self._collect_cookies()
        return res

    # ---------- cookie ----------
    def _collect_cookies(self):
        jar = self._session.cookie_jar
        wanted = ('sessionid', 'sessionid_ss', 'sid_tt', 'uid_tt', 'uid_tt_ss',
                  'passport_csrf_token', 'tt_token', 'sid_guard', 'ttwid')
        out = {}
        for c in jar:
            if c.key in wanted or c.key.endswith('_ss') or c.key.startswith('sid') or c.key == 'ttwid':
                out[c.key] = c.value
        self._cookies.update(out)
        # 持久化
        try:
            self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
            self.cookie_file.write_text(json.dumps({
                'saved_at': int(time.time()),
                'cookies': self._cookies,
            }, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

    def get_cookies(self) -> Dict[str, str]:
        return dict(self._cookies)

    def get_cookie_header(self) -> str:
        return '; '.join(f'{k}={v}' for k, v in self._cookies.items())

    @classmethod
    def load_cached_cookies(cls, cookie_file: Optional[Path] = None) -> Optional[Dict[str, str]]:
        p = cookie_file or SAVE_COOKIES_TO
        if not p.exists():
            return None
        try:
            obj = json.loads(p.read_text(encoding='utf-8'))
            cks = obj.get('cookies') or {}
            # 不按本地保存日期强制判定失效，由抖音服务端决定 sessionid 是否有效。
            if cks.get('sessionid'):
                return cks
            return None
        except Exception:
            return None

    @classmethod
    def load_danmu_server_cookies(
        cls,
        cookie_file: Optional[Path] = None,
        save_to: Optional[Path] = None,
    ) -> Optional[Dict[str, str]]:
        p = cookie_file or DANMU_SERVER_COOKIE_FILE
        if not p.exists():
            return None
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
            start = text.find('[')
            if start < 0:
                return None
            rows = json.loads(text[start:])
            now = datetime.now(timezone.utc)
            out: Dict[str, str] = {}
            for row in rows:
                domain = str(row.get('Domain') or '')
                name = str(row.get('Name') or '')
                value = str(row.get('Value') or '')
                if not name or 'douyin.com' not in domain:
                    continue
                expires = row.get('Expires') or ''
                if expires:
                    try:
                        exp = datetime.fromisoformat(str(expires).replace('Z', '+00:00'))
                        if exp <= now:
                            continue
                    except Exception:
                        pass
                out[name] = value
            if not out.get('sessionid'):
                return None
            target = save_to or SAVE_COOKIES_TO
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({
                'saved_at': int(time.time()),
                'source': str(p),
                'cookies': out,
            }, ensure_ascii=False, indent=2), encoding='utf-8')
            return out
        except Exception:
            return None


def _terminal_qr(qr_url: str) -> str:
    """用 qrcode 库在终端打印字符二维码"""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_url)
        qr.make(fit=True)
        # 用黑白方块
        mat = qr.get_matrix()
        lines = []
        for row in mat:
            lines.append(''.join('██' if c else '  ' for c in row))
        return '\n'.join(lines)
    except Exception:
        return f'扫码链接（请复制到支持扫码的设备或生成二维码）：\n{qr_url}'


async def interactive_login(proxy: Optional[str] = None) -> str:
    """
    交互式登录（命令行）：打印二维码到终端（文本），提示扫码，若需要二次验证则输入验证码。
    返回 cookie header 字符串。
    """
    cached = QrLogin.load_cached_cookies()
    if cached and cached.get('sessionid'):
        print('[auth] 使用缓存的 cookies (sessionid=', cached.get('sessionid','')[:8], '...)')
        return '; '.join(f'{k}={v}' for k, v in cached.items())

    async with QrLogin(proxy=proxy) as qr:
        info = await qr.fetch_qrcode()
        print('\n' + '='*50)
        print('请使用抖音 APP 扫描下方二维码登录：')
        print('='*50)
        print(_terminal_qr(info['qr_url']))
        if info['qr_url']:
            print('扫码URL:', info['qr_url'])
        print('='*50 + '\n')

        # 轮询扫码状态
        for _ in range(120):  # 约 2 分钟
            await asyncio.sleep(1.5)
            try:
                st = await qr.check_scan()
            except Exception as e:
                print('[auth] 查询扫码状态失败:', e)
                continue
            s = st['status']
            if s == 'waiting':
                continue
            if s == 'scanned':
                print('[auth] 已扫码，请在手机上确认登录...')
                continue
            if s == 'expired':
                print('[auth] 二维码已过期，请重新运行')
                sys.exit(1)
            if s in ('need_sms_verify', 'need_email_verify'):
                vi = st['verify_info'] or {}
                mode = '短信' if s == 'need_sms_verify' else '邮箱'
                mask = vi.get('mask') or vi.get('mobile') or vi.get('email') or ''
                print(f'[auth] 需要{mode}二次验证，目标：{mask}，正在发送验证码...')
                try:
                    res = await qr.send_verify_code()
                    print('[auth] 验证码已发送:', res.get('message') or '')
                except Exception as e:
                    print('[auth] 发送验证码失败:', e)
                code = input('请输入收到的验证码: ').strip()
                res2 = await qr.commit_verify_code(code)
                if qr.get_cookies().get('sessionid'):
                    break
                print('[auth] 验证码校验失败:', res2)
                sys.exit(1)
            if s == 'confirmed':
                break
        else:
            print('[auth] 超时未扫码')
            sys.exit(1)

        cks = qr.get_cookies()
        if not cks.get('sessionid'):
            print('[auth] 登录失败：未拿到 sessionid')
            sys.exit(1)
        print('[auth] 登录成功，cookies 已缓存到', qr.cookie_file)
        return qr.get_cookie_header()


if __name__ == '__main__':
    hdr = asyncio.run(interactive_login())
    print('\nCookie header 长度:', len(hdr))

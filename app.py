from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_caching import Cache
from bs4 import BeautifulSoup
import requests
from Crypto.Cipher import AES
import base64
import threading
import time

app = Flask(__name__)
CORS(app)

# Configure caching (default: in-memory, 5 min TTL)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 200})

class VignanStudentScraper:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://webprosindia.com/vignanit"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'DNT': '1',
            'Origin': 'https://webprosindia.com',
        }
        self.login_lock = threading.Lock()
        self.logged_in_sessions = {}  # Cache login sessions by regno

    def encrypt_password(self, password):
        key = b'8701661282118308'
        iv = b'8701661282118308'
        pad = lambda s: s + (16 - len(s) % 16) * chr(16 - len(s) % 16)
        password_padded = pad(password)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(password_padded.encode('utf-8'))
        return base64.b64encode(encrypted).decode('utf-8')

    def login(self, registration_number, password):
        """Login once per registration_number, cache session"""
        with self.login_lock:
            if registration_number in self.logged_in_sessions:
                return True, "Login session reused"

            login_url = f"{self.base_url}/Default.aspx"
            response = self.session.get(login_url, headers=self.headers)
            soup = BeautifulSoup(response.content, 'lxml')

            viewstate = soup.find('input', {'id': '__VIEWSTATE'})
            viewstategenerator = soup.find('input', {'id': '__VIEWSTATEGENERATOR'})
            eventvalidation = soup.find('input', {'id': '__EVENTVALIDATION'})

            login_data = {
                '__VIEWSTATE': viewstate['value'] if viewstate else '',
                '__VIEWSTATEGENERATOR': viewstategenerator['value'] if viewstategenerator else '',
                '__EVENTVALIDATION': eventvalidation['value'] if eventvalidation else '',
                'txtId2': registration_number,
                'txtPwd2': self.encrypt_password(password),
                'hdnpwd2': self.encrypt_password(password),
                'imgBtn2.x': '20',
                'imgBtn2.y': '9',
                'txtId1': '',
                'txtPwd1': '',
                'hdnpwd1': '',
                'txtId3': '',
                'txtPwd3': '',
                'hdnpwd3': ''
            }

            login_headers = self.headers.copy()
            login_headers['Referer'] = login_url
            login_headers['Content-Type'] = 'application/x-www-form-urlencoded'

            response = self.session.post(login_url, data=login_data, headers=login_headers)

            if 'StudentMaster.aspx' in response.url or 'StudentProfile' in response.text:
                self.logged_in_sessions[registration_number] = self.session
                return True, "Login successful"
            elif 'Please log out other student login' in response.text:
                return False, "Another student is already logged in"
            else:
                return False, "Invalid credentials"

    def get_student_performance_present(self, registration_number):
        """Fetch performance data (attendance & marks)"""
        ajax_url = f"{self.base_url}/ajax/StudentProfile,App_Web_studentprofile.aspx.a2a1b31c.ashx?_method=ShowStudentProfileNew&_session=rw"
        ajax_headers = self.headers.copy()
        ajax_headers.update({
            'Content-Type': 'text/plain;charset=UTF-8',
            'Referer': f'{self.base_url}/Academics/StudentProfile.aspx?scrid=17',
            'X-Requested-With': 'XMLHttpRequest'
        })

        post_data = f"RollNo={registration_number}\nisImageDisplay=false"

        try:
            response = self.session.post(ajax_url, data=post_data, headers=ajax_headers)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, 'lxml')
            performance_div = soup.find('div', {'id': 'divProfile_Present'})

            if not performance_div:
                # Fallback: search h1 with PERFORMANCE (Present)
                for h1 in soup.find_all('h1'):
                    if 'PERFORMANCE' in h1.get_text() and 'Present' in h1.get_text():
                        performance_div = h1.find_next_sibling('div')
                        if performance_div:
                            break

            if not performance_div:
                return None

            return self.extract_performance_present(performance_div)

        except Exception:
            return None

    def extract_performance_present(self, performance_div):
        data = {'attendance': [], 'total_attendance': {}, 'internal_marks': []}
        tables = performance_div.find_all('table')

        for table in tables:
            rows = table.find_all('tr')
            for idx, row in enumerate(rows):
                cells = [c.get_text(strip=True) for c in row.find_all('td')]
                if not cells:
                    continue

                if 'Subject' in cells and 'Held' in cells and 'Attend' in cells:
                    for data_row in rows[idx+1:]:
                        data_cells = data_row.find_all('td')
                        if not data_cells:
                            continue
                        first_cell = data_cells[0].get_text(strip=True)

                        if 'TOTAL' in first_cell.upper():
                            if len(data_cells) >= 5:
                                data['total_attendance'] = {
                                    'held': data_cells[2].get_text(strip=True),
                                    'attended': data_cells[3].get_text(strip=True),
                                    'percentage': data_cells[4].get_text(strip=True)
                                }
                            break

                        if first_cell.isdigit() and len(data_cells) >= 5:
                            data['attendance'].append({
                                'sl_no': data_cells[0].get_text(strip=True),
                                'subject': data_cells[1].get_text(strip=True),
                                'classes_held': data_cells[2].get_text(strip=True),
                                'classes_attended': data_cells[3].get_text(strip=True),
                                'attendance_percentage': data_cells[4].get_text(strip=True)
                            })
                    break
            if data['attendance']:
                break
        return data


scraper = VignanStudentScraper()


@app.route('/attendance', methods=['GET'])
def get_attendance():
    regno = request.args.get('regno')
    password = request.args.get('password')

    if not regno or not password:
        return jsonify({'success': False, 'error': 'Missing regno or password'}), 400

    # Check cache first
    cache_key = f"attendance:{regno}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify(cached)

    login_success, login_msg = scraper.login(regno, password)
    if not login_success:
        return jsonify({'success': False, 'error': login_msg}), 401

    data = scraper.get_student_performance_present(regno)
    if not data:
        return jsonify({'success': False, 'error': 'Failed to fetch performance data'}), 500

    result = {'success': True, 'registration_number': regno, 'data': data}
    cache.set(cache_key, result)
    return jsonify(result)


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'message': 'Vignan Student Attendance API',
        'usage': 'GET /attendance?regno=YOUR_REGNO&password=YOUR_PASSWORD'
    })


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)

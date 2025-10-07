from flask import Flask, request, jsonify
import requests
from flask_cors import CORS
from bs4 import BeautifulSoup
import json
from Crypto.Cipher import AES
import base64

app = Flask(__name__)
CORS(app)
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

    def encrypt_password(self, password):
        """Encrypt password using AES as done in the JavaScript"""
        key = b'8701661282118308'
        iv = b'8701661282118308'

        # Pad the password to be multiple of 16 bytes
        pad = lambda s: s + (16 - len(s) % 16) * chr(16 - len(s) % 16)
        password_padded = pad(password)

        # Create AES cipher
        cipher = AES.new(key, AES.MODE_CBC, iv)

        # Encrypt
        encrypted = cipher.encrypt(password_padded.encode('utf-8'))

        # Return base64 encoded
        return base64.b64encode(encrypted).decode('utf-8')

    def login(self, registration_number, password):
        """Login to the student portal using registration number and password"""
        login_url = f"{self.base_url}/Default.aspx"

        # First, get the login page to extract hidden fields
        response = self.session.get(login_url, headers=self.headers)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract hidden form fields
        viewstate = soup.find('input', {'id': '__VIEWSTATE'})['value'] if soup.find('input', {'id': '__VIEWSTATE'}) else ''
        viewstategenerator = soup.find('input', {'id': '__VIEWSTATEGENERATOR'})['value'] if soup.find('input', {'id': '__VIEWSTATEGENERATOR'}) else ''
        eventvalidation = soup.find('input', {'id': '__EVENTVALIDATION'})['value'] if soup.find('input', {'id': '__EVENTVALIDATION'}) else ''

        # Encrypt the password
        encrypted_password = self.encrypt_password(password)

        # Prepare login data for student login (second form - imgBtn2)
        login_data = {
            '__VIEWSTATE': viewstate,
            '__VIEWSTATEGENERATOR': viewstategenerator,
            '__EVENTVALIDATION': eventvalidation,
            'txtId2': registration_number,
            'txtPwd2': encrypted_password,
            'hdnpwd2': encrypted_password,
            'imgBtn2.x': '20',
            'imgBtn2.y': '9',
            'txtId1': '',
            'txtPwd1': '',
            'hdnpwd1': '',
            'txtId3': '',
            'txtPwd3': '',
            'hdnpwd3': ''
        }

        # Update referer for the POST request
        login_headers = self.headers.copy()
        login_headers['Referer'] = login_url
        login_headers['Content-Type'] = 'application/x-www-form-urlencoded'

        # Perform login
        response = self.session.post(login_url, data=login_data, headers=login_headers)

        # Check if login was successful
        if 'StudentMaster.aspx' in response.url or 'StudentProfile' in response.text:
            return True, "Login successful"
        elif 'Please log out other student login' in response.text:
            return False, "Another student is already logged in"
        else:
            return False, "Invalid credentials"

    def get_student_performance_present(self, registration_number):
        """Get student's current performance data via AJAX endpoint"""
        # AJAX endpoint for student profile
        ajax_url = f"{self.base_url}/ajax/StudentProfile,App_Web_studentprofile.aspx.a2a1b31c.ashx?_method=ShowStudentProfileNew&_session=rw"

        # Prepare AJAX request headers
        ajax_headers = self.headers.copy()
        ajax_headers['Content-Type'] = 'text/plain;charset=UTF-8'
        ajax_headers['Referer'] = f'{self.base_url}/Academics/StudentProfile.aspx?scrid=17'
        ajax_headers['X-Requested-With'] = 'XMLHttpRequest'

        # Prepare the POST data
        post_data = f"RollNo={registration_number}\nisImageDisplay=false"

        try:
            # Make the AJAX request
            response = self.session.post(ajax_url, data=post_data, headers=ajax_headers)

            if response.status_code == 200:
                # Parse the HTML response
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find the "PERFORMANCE (Present)" section
                performance_present = soup.find('div', {'id': 'divProfile_Present'})

                if performance_present:
                    return self.extract_performance_present(performance_present)
                else:
                    # Try alternative: find h1 with text "PERFORMANCE (Present)" and get next div
                    h1_tags = soup.find_all('h1')
                    for h1 in h1_tags:
                        if 'PERFORMANCE' in h1.get_text() and 'Present' in h1.get_text():
                            next_div = h1.find_next_sibling('div')
                            if next_div:
                                return self.extract_performance_present(next_div)

                    return None
            else:
                return None

        except Exception as e:
            return None

    def extract_performance_present(self, performance_div):
        """Extract attendance and internal marks from PERFORMANCE (Present) section"""
        performance_data = {
            'attendance': [],
            'total_attendance': {},
            'internal_marks': []
        }

        # Find all tables in the performance section
        tables = performance_div.find_all('table')

        # Look for the attendance table
        for table in tables:
            all_rows = table.find_all('tr')

            # Look through all rows to find one with attendance headers
            for row in all_rows:
                cells = row.find_all('td')
                if cells:
                    cell_texts = [c.get_text(strip=True) for c in cells]

                    # Check if this row has the attendance headers
                    if 'Subject' in cell_texts and 'Held' in cell_texts and 'Attend' in cell_texts:
                        # Extract all data rows after this header
                        header_idx = all_rows.index(row)
                        data_rows = all_rows[header_idx + 1:]

                        for data_row in data_rows:
                            data_cells = data_row.find_all('td')

                            if len(data_cells) >= 5:
                                first_cell = data_cells[0].get_text(strip=True)

                                # Check if this is TOTAL row
                                if 'TOTAL' in first_cell.upper():
                                    if len(data_cells) == 5:
                                        performance_data['total_attendance'] = {
                                            'held': data_cells[2].get_text(strip=True),
                                            'attended': data_cells[3].get_text(strip=True),
                                            'percentage': data_cells[4].get_text(strip=True)
                                        }
                                    else:
                                        performance_data['total_attendance'] = {
                                            'held': data_cells[1].get_text(strip=True),
                                            'attended': data_cells[2].get_text(strip=True),
                                            'percentage': data_cells[3].get_text(strip=True)
                                        }
                                    break

                                # Check if this is a data row (starts with a number)
                                if first_cell.isdigit():
                                    performance_data['attendance'].append({
                                        'sl_no': data_cells[0].get_text(strip=True),
                                        'subject': data_cells[1].get_text(strip=True),
                                        'classes_held': data_cells[2].get_text(strip=True),
                                        'classes_attended': data_cells[3].get_text(strip=True),
                                        'attendance_percentage': data_cells[4].get_text(strip=True)
                                    })

                        break

            if performance_data['attendance']:
                break

        return performance_data


@app.route('/attendance', methods=['GET'])
def get_attendance():
    """
    Endpoint to fetch student attendance data
    URL format: /attendance?regno=YOUR_REGNO&password=YOUR_PASSWORD
    """
    # Get parameters from URL
    registration_number = request.args.get('regno')
    password = request.args.get('password')

    # Validate inputs
    if not registration_number or not password:
        return jsonify({
            'success': False,
            'error': 'Missing required parameters. Please provide regno and password.'
        }), 400

    try:
        # Create scraper instance
        scraper = VignanStudentScraper()

        # Attempt login
        login_success, login_message = scraper.login(registration_number, password)

        if not login_success:
            return jsonify({
                'success': False,
                'error': login_message
            }), 401

        # Fetch performance data
        performance_data = scraper.get_student_performance_present(registration_number)

        if performance_data:
            return jsonify({
                'success': True,
                'registration_number': registration_number,
                'data': performance_data
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch performance data'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500


@app.route('/', methods=['GET'])
def home():
    """Home endpoint with API documentation"""
    return jsonify({
        'message': 'Vignan Student Attendance API',
        'usage': 'GET /attendance?regno=YOUR_REGNO&password=YOUR_PASSWORD',
        'example': '/attendance?regno=20981A05K1&password=yourpassword'
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

from flask import Flask, render_template, request, redirect, url_for, session
from config import SECRET_KEY

app = Flask(__name__)
app.secret_key = SECRET_KEY

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/menu')
def info():
    return render_template('menu.html')

@app.route('/contact')
def contact():
    return render_template('contacts.html')

@app.route('/service')
def service():
    return render_template('services.html')

@app.route('/rooms')
def rooms():
    return render_template('rooms.html')

@app.route('/house', methods=['GET', 'POST'])
def house():
    if request.method == 'POST':
        data = request.get_json()
        session['house_data'] = data
        return '', 204

    data = session.get('house_data')
    
    return render_template(
        'house.html',
        data=data
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
from flask import Flask, flash, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from sqlalchemy.sql.expression import func
import uuid
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
# Change to SQLite URI
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///easter_egg_game.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)

# Define the Player model
class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    score = db.Column(db.Integer, default=0)

# Define the Egg model
class Egg(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    points = db.Column(db.Integer, nullable=False)

# Define the PlayerEgg model to track which eggs each player has scanned
class PlayerEgg(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    egg_id = db.Column(db.String(36), db.ForeignKey('egg.id'), nullable=False)

# Get the leaderboard of players
def get_leaderboard():
    app.logger.info("leaderboard carregado!!")
    players = Player.query.order_by(Player.score.desc()).all()
    return [{'name': p.name, 'score': p.score} for p in players]

# Signup route for the players
@app.route('/', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            player = Player.query.filter_by(name=name).first()
            if not player:
                player = Player(name=name)
                db.session.add(player)
                db.session.commit()
                # Broadcast leaderboard update
                socketio.emit('update_leaderboard', get_leaderboard())
            session['player_name'] = name
            return redirect(url_for('leaderboard'))
    return render_template('signup.html')

# Egg scan route to validate and update scores
@app.route('/scan/<uuid:egg_id>')
def scan(egg_id):
    if 'player_name' not in session:
        return redirect(url_for('signup'))
    
    egg_id = str(egg_id).lower()
    
    player = Player.query.filter_by(name=session['player_name']).first()
    egg = Egg.query.filter_by(id=egg_id).first()
    
    app.logger.info("player: %s, egg: %s", player, egg)
    
    if player and egg:
        # Check if player has already scanned this egg
        existing_scan = PlayerEgg.query.filter_by(player_id=player.id, egg_id=egg.id).first()
        if existing_scan:
            return jsonify({'message': 'Egg already scanned!', 'total_points': player.score})
        
        # Record the scan and update score
        player.score += egg.points
        db.session.add(PlayerEgg(player_id=player.id, egg_id=egg.id))
        db.session.commit()
        
        # Broadcast leaderboard update
        socketio.emit('update_leaderboard', get_leaderboard())
        
        return jsonify({'message': 'Egg scanned!', 'total_points': player.score})
    return jsonify({'message': 'Egg not found'}), 400

# Leaderboard route
@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html', leaderboard=get_leaderboard())

# Manager route
@app.route('/eggs', methods=['GET'])
def egg_list():
    # Retrieves eggs sorted by score
    eggs = Egg.query.order_by(Egg.points.desc()).all()
    return render_template('eggs/list.html', eggs=eggs)

@app.route('/eggs/create', methods=['GET', 'POST'])
def egg_create():
    # Create new egg
    if request.method == 'POST':
        points = request.form.get('points')
        app.logger.info("creating egg with points: %s", points)
        new_egg = Egg(points=request.form.get('points'))
        db.session.add(new_egg)
        db.session.commit()
        flash('Egg created successfully', category='success')
        return redirect(url_for('egg_list'))
    return render_template('eggs/create.html')
    
@app.route('/eggs/update/<string:egg_id>', methods=['GET', 'POST'])
def egg_update(egg_id):
    # Modify points of one existent egg
    if request.method == 'POST':
        points = request.form.get('points')

        egg = Egg.query.get(egg_id)
        if egg:
            app.logger.info("updating egg with points: %s", points)
             # Check if the new points are different from the current points
            egg.points = int(points)
            db.session.commit()
            flash('Egg modify successfully', category='success')
        else:
            flash('Egg not found', category='error')
        return redirect(url_for('egg_list'))
    return render_template('eggs/update.html', egg=Egg.query.get(str(egg_id).lower()))

@app.route('/eggs/<string:egg_id>', methods=['POST'])
def egg_delete(egg_id):
    egg = Egg.query.get(egg_id)
    if egg:
        db.session.delete(egg)
        db.session.commit()
        flash('Egg deleted successfully', category='success')   
    return redirect(url_for('egg_list'))
    
@app.route('/reset/<int:generate_new_ids>')
def reset(generate_new_ids):
    db.create_all()
    db.session.query(PlayerEgg).delete()
    db.session.query(Player).delete()
    db.session.commit()
    
    if generate_new_ids == 1:
        # Delete all eggs and create new eggs with new ids
        db.session.query(Egg).delete()
        db.session.commit()
        
        for _ in range(25):
            egg = Egg(points=random.randint(10, 50))
            db.session.add(egg)
        db.session.commit()
    else:
        # Don't reset the points of eggs and don't change the ids
        eggs = Egg.query.all()
        db.session.commit()
    
    eggs = Egg.query.order_by(Egg.points.desc()).all()
    return render_template('reset.html', eggs=eggs)

# Handle WebSocket connection to send updates
@socketio.on('connect')
def handle_connect():
    emit('update_leaderboard', get_leaderboard())

if __name__ == '__main__':
    # Initialize the database
    # db.create_all()
    socketio.run(app, debug=True)

import streamlit as st
import mysql.connector
import hashlib
from datetime import datetime
import pandas as pd
from PIL import Image, ImageFont, ImageDraw
import os
import streamlit.components.v1 as components
import plotly.graph_objects as go
from urllib.parse import urlparse, parse_qs
from config import get_database_connection
from pymysql.cursors import DictCursor

# Constants for file paths
LOGO_DIR = "team_logos"  # Directory containing team logos

# # Database Configuration
# def get_database_connection():
#     return mysql.connector.connect(
#         host="localhost",
#         user="root",
#         password="root",
#         database="fantasy_appc"
#     )

# Initialize database tables
def init_db():
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Create users table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            points INT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            team VARCHAR(100) NOT NULL,
            position ENUM('GK', 'DEF', 'MID', 'FWD') NOT NULL,
            price DECIMAL(10,2) NOT NULL,
            points INT DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_teams (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            player_id INT NOT NULL,
            position_order INT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    """)
    
    # Modified matches table to store local image paths
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INT AUTO_INCREMENT PRIMARY KEY,
            home_team VARCHAR(100) NOT NULL,
            away_team VARCHAR(100) NOT NULL,
            match_time DATETIME NOT NULL,
            home_logo VARCHAR(255),
            away_logo VARCHAR(255),
            status ENUM('upcoming', 'live', 'completed') DEFAULT 'upcoming'
        )
    """)

    # Add new table for squad history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS squad_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            total_points INT DEFAULT 0,
            locked_until DATETIME NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS squad_players (
            squad_id INT NOT NULL,
            player_id INT NOT NULL,
            position_order INT NOT NULL,
            points_earned INT DEFAULT 0,
            FOREIGN KEY (squad_id) REFERENCES squad_history(id),
            FOREIGN KEY (player_id) REFERENCES players(id),
            PRIMARY KEY (squad_id, player_id)
        )
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    # Set up admin user
    setup_admin()

# Helper function to load team logo
def load_team_logo(team_name):
    try:
        # Convert team name to filename format (lowercase, no spaces)
        filename = f"{team_name.lower().replace(' ', '')}.jpg"
        image_path = os.path.join(LOGO_DIR, filename)
        
        # Check if file exists
        if os.path.exists(image_path):
            return Image.open(image_path)
        else:
            # Return a default image or placeholder
            return None
    except Exception as e:
        st.error(f"Error loading logo for {team_name}: {str(e)}")
        return None

# Authentication functions remain the same
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        hashed_pw = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hashed_pw)
        )
        conn.commit()
        return True
    except mysql.connector.Error as err:
        st.error(f"Registration failed: {err}")
        return False
    finally:
        cursor.close()
        conn.close()

def login_user(username, password):
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    hashed_pw = hash_password(password)
    cursor.execute(
        "SELECT * FROM users WHERE username = %s AND password = %s",
        (username, hashed_pw)
    )
    user = cursor.fetchone()
    
    cursor.close()
    conn.close()
    return user

def get_leaderboard():
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT username, points
        FROM users
        ORDER BY points DESC
        LIMIT 10
    """)
    
    leaderboard = cursor.fetchall()
    cursor.close()
    conn.close()
    return leaderboard

def get_popular_players():
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    # Get most selected players
    cursor.execute("""
        SELECT 
            p.name,
            p.position,
            p.team,
            p.price,
            p.points,
            COUNT(sp.player_id) as selection_count,
            COUNT(sp.player_id) * 100.0 / (
                SELECT COUNT(DISTINCT user_id) 
                FROM squad_history
            ) as selection_percentage
        FROM players p
        LEFT JOIN squad_players sp ON p.id = sp.player_id
        GROUP BY p.id
        ORDER BY selection_count DESC
        LIMIT 10
    """)
    
    popular_players = cursor.fetchall()
    cursor.close()
    conn.close()
    return popular_players

# Add these SQL commands to set up the admin user
def setup_admin():
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # First, add is_admin column if it doesn't exist
    try:
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE
        """)
        
        # Create an admin user if it doesn't exist
        cursor.execute("""
            INSERT INTO users (username, password, is_admin)
            SELECT 'admin', %s, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM users WHERE username = 'admin'
            )
        """, (hash_password('admin123'),))
        
        conn.commit()
    except Exception as e:
        print(f"Error setting up admin: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def get_top_scoring_players():
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT 
            name,
            position,
            team,
            price,
            points
        FROM players
        ORDER BY points DESC
        LIMIT 10
    """)
    
    top_scorers = cursor.fetchall()
    cursor.close()
    conn.close()
    return top_scorers

# Add these visualizations to your dashboard
def add_dashboard_visualizations():
    # Popular Players
    st.header("Most Selected Players")
    popular_players = get_popular_players()
    if popular_players:
        df_popular = pd.DataFrame(popular_players)
        fig = go.Figure(data=[
            go.Bar(
                x=df_popular['name'],
                y=df_popular['selection_percentage'],
                text=df_popular['selection_percentage'].round(2).astype(str) + '%',
                textposition='auto',
            )
        ])
        fig.update_layout(
            title="Player Selection Rate",
            xaxis_title="Player Name",
            yaxis_title="Selection Percentage (%)",
            yaxis_range=[0, 100]
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Top Scoring Players
    st.header("Top Scoring Players")
    top_scorers = get_top_scoring_players()
    if top_scorers:
        df_scores = pd.DataFrame(top_scorers)
        fig = go.Figure(data=[
            go.Bar(
                x=df_scores['name'],
                y=df_scores['points'],
                text=df_scores['points'],
                textposition='auto',
            )
        ])
        fig.update_layout(
            title="Player Points",
            xaxis_title="Player Name",
            yaxis_title="Total Points"
        )
        st.plotly_chart(fig, use_container_width=True)

def get_user_points_history(user_id):
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT 
            sh.created_at as matchday,
            sh.total_points,
            SUM(sp.points_earned) as matchday_points
        FROM squad_history sh
        JOIN squad_players sp ON sh.id = sp.squad_id
        WHERE sh.user_id = %s
        GROUP BY sh.id
        ORDER BY sh.created_at
    """, (user_id,))
    
    points_history = cursor.fetchall()
    cursor.close()
    conn.close()
    return points_history

def get_team_composition_stats(user_id):
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT 
            p.team,
            COUNT(*) as player_count
        FROM squad_history sh
        JOIN squad_players sp ON sh.id = sp.squad_id
        JOIN players p ON sp.player_id = p.id
        WHERE sh.user_id = %s
        AND sh.created_at = (
            SELECT MAX(created_at)
            FROM squad_history
            WHERE user_id = %s
        )
        GROUP BY p.team
    """, (user_id, user_id))
    
    composition = cursor.fetchall()
    cursor.close()
    conn.close()
    return composition

def get_position_points_distribution(user_id):
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT 
            p.position,
            SUM(sp.points_earned) as total_points,
            AVG(sp.points_earned) as avg_points
        FROM squad_history sh
        JOIN squad_players sp ON sh.id = sp.squad_id
        JOIN players p ON sp.player_id = p.id
        WHERE sh.user_id = %s
        GROUP BY p.position
    """, (user_id,))
    
    position_stats = cursor.fetchall()
    cursor.close()
    conn.close()
    return position_stats

def get_upcoming_matches():
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT *
        FROM matches
        WHERE match_time > NOW()
        ORDER BY match_time
        LIMIT 5
    """)
    
    matches = cursor.fetchall()
    cursor.close()
    conn.close()
    return matches

def get_youtube_id(url):
    """Extract YouTube video ID from URL"""
    parsed = urlparse(url)
    if parsed.hostname == 'youtu.be':
        return parsed.path[1:]
    if parsed.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed.path == '/watch':
            p = parse_qs(parsed.query)
            return p['v'][0]
        if parsed.path[:7] == '/embed/':
            return parsed.path.split('/')[2]
        if parsed.path[:3] == '/v/':
            return parsed.path.split('/')[2]
    return None

# Add these new functions
def get_available_players(position):
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT * FROM players 
        WHERE position = %s 
        ORDER BY points DESC
    """, (position,))
    
    players = cursor.fetchall()
    cursor.close()
    conn.close()
    # Convert Decimal prices to float
    for player in players:
        player['price'] = float(player['price'])
    return players

def get_player_by_id(player_id):
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    cursor.execute("SELECT * FROM players WHERE id = %s", (player_id,))
    player = cursor.fetchone()
    cursor.close()
    conn.close()
    if player:
        player['price'] = float(player['price'])  # Convert Decimal to float
    return player

# Add these new functions for squad management
def get_current_squad_lock(user_id):
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT locked_until 
        FROM squad_history 
        WHERE user_id = %s 
        ORDER BY created_at DESC 
        LIMIT 1
    """, (user_id,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if result:
        return result['locked_until']
    return None

def save_squad_history(user_id, selected_players):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        # Calculate lock until time (24 hours from now)
        from datetime import datetime, timedelta
        lock_until = datetime.now() + timedelta(days=1)
        
        # Insert into squad_history
        cursor.execute("""
            INSERT INTO squad_history (user_id, locked_until)
            VALUES (%s, %s)
        """, (user_id, lock_until))
        
        squad_id = cursor.lastrowid
        
        # Insert all players
        for pos_order, player_id in enumerate(selected_players):
            cursor.execute("""
                INSERT INTO squad_players (squad_id, player_id, position_order)
                VALUES (%s, %s, %s)
            """, (squad_id, player_id, pos_order))
        
        conn.commit()
        return True, lock_until
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def update_user_points():
    """Update points for all users based on their current squad's performance"""
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        # Get all users with their latest squad
        cursor.execute("""
            SELECT DISTINCT u.id as user_id, u.username
            FROM users u
            JOIN squad_history sh ON u.id = sh.user_id
        """)
        users = cursor.fetchall()
        
        print(f"Found {len(users)} users with squads")  # Debug print
        
        for user in users:
            print(f"Processing user: {user['username']}")  # Debug print
            
            # Get user's latest squad
            cursor.execute("""
                SELECT 
                    sh.id as squad_id,
                    p.id as player_id,
                    p.name as player_name,
                    p.points as player_points,
                    COALESCE(sp.points_earned, 0) as points_already_earned
                FROM squad_history sh
                JOIN squad_players sp ON sh.id = sp.squad_id
                JOIN players p ON sp.player_id = p.id
                WHERE sh.user_id = %s
                AND sh.created_at = (
                    SELECT MAX(created_at)
                    FROM squad_history
                    WHERE user_id = %s
                )
            """, (user['user_id'], user['user_id']))
            
            squad = cursor.fetchall()
            
            if squad:
                print(f"Found squad with {len(squad)} players")  # Debug print
                total_new_points = 0
                
                # Calculate new points earned
                for player in squad:
                    points_to_add = player['player_points'] - player['points_already_earned']
                    print(f"Player: {player['player_name']}, Current points: {player['player_points']}, "
                          f"Already earned: {player['points_already_earned']}, To add: {points_to_add}")  # Debug print
                    
                    if points_to_add > 0:
                        total_new_points += points_to_add
                        
                        # Update points_earned in squad_players
                        cursor.execute("""
                            UPDATE squad_players 
                            SET points_earned = %s
                            WHERE squad_id = %s AND player_id = %s
                        """, (player['player_points'], player['squad_id'], player['player_id']))
                
                print(f"Total new points to add: {total_new_points}")  # Debug print
                
                if total_new_points > 0:
                    # Update total points for the squad
                    cursor.execute("""
                        UPDATE squad_history
                        SET total_points = total_points + %s
                        WHERE id = %s
                    """, (total_new_points, squad[0]['squad_id']))
                    
                    # Update user's total points
                    cursor.execute("""
                        UPDATE users
                        SET points = points + %s
                        WHERE id = %s
                    """, (total_new_points, user['user_id']))
                    
                    print(f"Updated points for user {user['username']}")  # Debug print
            else:
                print(f"No current squad found for user {user['username']}")  # Debug print
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Error updating user points: {str(e)}")
        print(f"Error type: {type(e)}")  # Print error type
        import traceback
        print(f"Traceback: {traceback.format_exc()}")  # Print full traceback
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def calculate_player_rating(player):
    """
    Calculate a rating for each player based on their performance metrics
    """
    # Base rating from points
    rating = player['points'] * 1.5
    
    # Adjust rating based on price (value for money)
    price = float(player['price'])
    if price > 0:
        value_ratio = rating / price
        rating *= (1 + value_ratio / 10)  # Boost rating for players who deliver good value
    
    return rating

def get_all_players_with_stats():
    """
    Get all players with their performance statistics
    """
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT p.*,
               COUNT(sp.player_id) as times_selected,
               AVG(sp.points_earned) as avg_points_per_game
        FROM players p
        LEFT JOIN squad_players sp ON p.id = sp.player_id
        GROUP BY p.id
    """)
    
    players = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # Convert price to float and calculate ratings
    for player in players:
        player['price'] = float(player['price'])
        player['rating'] = calculate_player_rating(player)
    
    return players

def suggest_team(budget=100.0):
    """
    Suggest an optimal team based on player performances and budget constraints
    """
    all_players = get_all_players_with_stats()
    
    # Separate players by position
    goalkeepers = [p for p in all_players if p['position'] == 'GK']
    defenders = [p for p in all_players if p['position'] == 'DEF']
    midfielders = [p for p in all_players if p['position'] == 'MID']
    forwards = [p for p in all_players if p['position'] == 'FWD']
    
    # Sort each list by rating
    goalkeepers.sort(key=lambda x: x['rating'], reverse=True)
    defenders.sort(key=lambda x: x['rating'], reverse=True)
    midfielders.sort(key=lambda x: x['rating'], reverse=True)
    forwards.sort(key=lambda x: x['rating'], reverse=True)
    
    def try_combination(gk, defs, mids, fwds):
        """Check if a combination of players fits within budget"""
        total_cost = (
            gk['price'] +
            sum(p['price'] for p in defs) +
            sum(p['price'] for p in mids) +
            sum(p['price'] for p in fwds)
        )
        return total_cost <= budget
    
    # Start with the best rated players
    suggested_gk = goalkeepers[0]
    suggested_defs = defenders[:4]
    suggested_mids = midfielders[:4]
    suggested_fwds = forwards[:2]
    
    # If over budget, try different combinations
    if not try_combination(suggested_gk, suggested_defs, suggested_mids, suggested_fwds):
        # Try different combinations by replacing expensive players with next best options
        for gk in goalkeepers:
            for i in range(len(defenders) - 3):
                for j in range(len(midfielders) - 3):
                    for k in range(len(forwards) - 1):
                        current_defs = defenders[i:i+4]
                        current_mids = midfielders[j:j+4]
                        current_fwds = forwards[k:k+2]
                        
                        if try_combination(gk, current_defs, current_mids, current_fwds):
                            suggested_gk = gk
                            suggested_defs = current_defs
                            suggested_mids = current_mids
                            suggested_fwds = current_fwds
                            break
    
    return {
        'GK': suggested_gk,
        'DEF': suggested_defs,
        'MID': suggested_mids,
        'FWD': suggested_fwds,
        'total_cost': (
            suggested_gk['price'] +
            sum(p['price'] for p in suggested_defs) +
            sum(p['price'] for p in suggested_mids) +
            sum(p['price'] for p in suggested_fwds)
        )
    }

def get_user_squad_history(user_id):
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT sh.*, 
               GROUP_CONCAT(p.name) as player_names,
               GROUP_CONCAT(sp.points_earned) as player_points
        FROM squad_history sh
        JOIN squad_players sp ON sh.id = sp.squad_id
        JOIN players p ON sp.player_id = p.id
        WHERE sh.user_id = %s
        GROUP BY sh.id
        ORDER BY sh.created_at DESC
    """, (user_id,))
    
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return history

def update_create_team_page():
    """
    Modify the create team page to include AI suggestion feature
    """
    # Add this at the beginning of your show_create_team function
    if st.sidebar.button("Get AI Suggested Team"):
        with st.spinner("AI analyzing player performances..."):
            suggested_team = suggest_team()
            
            # Update session state with suggested players
            st.session_state.selected_players = {
                'GK': suggested_team['GK']['id'],
                'DEF': [p['id'] for p in suggested_team['DEF']],
                'MID': [p['id'] for p in suggested_team['MID']],
                'FWD': [p['id'] for p in suggested_team['FWD']]
            }
            st.session_state.used_budget = suggested_team['total_cost']
            
            # Show suggestion summary
            st.sidebar.success(f"""
                Team suggested! Total cost: ₹{suggested_team['total_cost']:.2f}Cr
                
                Key players:
                - GK: {suggested_team['GK']['name']}
                - Top DEF: {suggested_team['DEF'][0]['name']}
                - Top MID: {suggested_team['MID'][0]['name']}
                - Top FWD: {suggested_team['FWD'][0]['name']}
            """)
            
            # Add explanation of selection
            st.sidebar.info("""
                Team selection based on:
                - Player performance points
                - Value for money
                - Historical consistency
                - Position balance
            """)
            
            st.rerun()  # Refresh the page to show selected players

def save_user_team(user_id, selected_players):
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        # Clear existing team
        cursor.execute("DELETE FROM user_teams WHERE user_id = %s", (user_id,))
        
        # Insert new team
        for pos_order, player_id in enumerate(selected_players):
            cursor.execute("""
                INSERT INTO user_teams (user_id, player_id, position_order)
                VALUES (%s, %s, %s)
            """, (user_id, player_id, pos_order))
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error saving team: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()

def is_admin(username):
    """Check if the user is an admin"""
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT is_admin FROM users WHERE username = %s
        """, (username,))
        
        result = cursor.fetchone()
        # Add debug print
        print(f"Admin check for {username}: {result}")
        return result and result['is_admin'] == 1
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_matches_for_date(date):
    """Get all matches scheduled for a specific date"""
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT id, home_team, away_team, match_time
        FROM matches
        WHERE DATE(match_time) = DATE(%s)
        AND status != 'completed'
    """, (date,))
    
    matches = cursor.fetchall()
    cursor.close()
    conn.close()
    return matches

def get_team_players(team):
    """Get all players from a specific team"""
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT id, name, position
        FROM players
        WHERE team = %s
    """, (team,))
    
    players = cursor.fetchall()
    cursor.close()
    conn.close()
    return players

def update_player_points(player_id, points_to_add):
    """Update player points"""
    conn = get_database_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE players
        SET points = points + %s
        WHERE id = %s
    """, (points_to_add, player_id))
    
    conn.commit()
    cursor.close()
    conn.close()

def record_match_result(match_id, home_score, away_score, status='completed'):
    """Record the match result"""
    conn = get_database_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE matches
        SET home_score = %s, away_score = %s, status = %s
        WHERE id = %s
    """, (home_score, away_score, status, match_id))
    
    conn.commit()
    cursor.close()
    conn.close()

def show_sidebar_navigation():
    """
    Show consistent sidebar navigation based on current page and user status
    """
    with st.sidebar:
        st.title("Navigation")
        
        # Show user info if logged in
        if st.session_state.user:
            st.info(f"Logged in as: {st.session_state.user['username']}")
            st.metric("Total Points", st.session_state.user['points'])
        
        # Sidebar navigation based on current page
        if st.session_state.page == 'dashboard':
            if st.button("📊 Team Analysis", key="nav_analysis"):
                st.session_state.page = 'team_analysis'
                st.rerun()
            
            if st.button("🎮 Create Team", key="nav_create"):
                st.session_state.page = 'create_team'
                st.rerun()
            
            # Admin button only shown for admin users
            if is_admin(st.session_state.user['username']):
                if st.button("🔐 Admin Panel", key="nav_admin", type="primary"):
                    st.session_state.page = 'admin'
                    st.rerun()
        
        elif st.session_state.page == 'create_team':
            # AI suggestion button
            if st.button("🤖 Get AI Suggested Team", key="nav_ai_suggest"):
                with st.spinner("AI analyzing player performances..."):
                    suggested_team = suggest_team()
                    st.session_state.selected_players = {
                        'GK': suggested_team['GK']['id'],
                        'DEF': [p['id'] for p in suggested_team['DEF']],
                        'MID': [p['id'] for p in suggested_team['MID']],
                        'FWD': [p['id'] for p in suggested_team['FWD']]
                    }
                    st.session_state.used_budget = suggested_team['total_cost']
                    
                    st.success(f"""
                        Team suggested! Total cost: ₹{suggested_team['total_cost']:.2f}Cr
                        
                        Key players:
                        - GK: {suggested_team['GK']['name']}
                        - Top DEF: {suggested_team['DEF'][0]['name']}
                        - Top MID: {suggested_team['MID'][0]['name']}
                        - Top FWD: {suggested_team['FWD'][0]['name']}
                    """)
                    st.rerun()
            
            if st.button("📊 Team Analysis", key="nav_analysis_create"):
                st.session_state.page = 'team_analysis'
                st.rerun()
        
        elif st.session_state.page == 'team_analysis':
            if st.button("🎮 Create Team", key="nav_create_analysis"):
                st.session_state.page = 'create_team'
                st.rerun()
        
        elif st.session_state.page == 'admin':
            if st.button("📊 Team Analysis", key="nav_analysis_admin"):
                st.session_state.page = 'team_analysis'
                st.rerun()
            
            if st.button("🎮 Create Team", key="nav_create_admin"):
                st.session_state.page = 'create_team'
                st.rerun()
        
        # Common buttons for logged-in users
        if st.session_state.user:
            st.markdown("---")  # Add a separator
            
            if st.session_state.page != 'dashboard':
                if st.button("🏠 Dashboard", key="nav_dashboard"):
                    st.session_state.page = 'dashboard'
                    st.rerun()
            
            if st.button("🚪 Logout", key="nav_logout", type="secondary"):
                st.session_state.user = None
                st.session_state.page = 'login'
                st.rerun()

def get_match_highlights():
    """Get match highlights from database"""
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_highlights (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            youtube_url VARCHAR(255) NOT NULL,
            match_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        SELECT * FROM match_highlights 
        ORDER BY match_date DESC 
        LIMIT 10
    """)
    
    highlights = cursor.fetchall()
    cursor.close()
    conn.close()
    return highlights

def show_highlights_section():
    """Display match highlights with video player"""
    st.header("Match Highlights")
    
    # Get highlights from database
    highlights = get_match_highlights()
    
    if not highlights:
        # Sample data if no highlights in database
        highlights = [
            {
                "title": "Mumbai City FC vs Bengaluru FC Highlights",
                "youtube_url": "https://www.youtube.com/watch?v=example1",
                "match_date": "2024-02-01"
            },
            {
                "title": "Kerala Blasters vs Mohun Bagan Highlights",
                "youtube_url": "https://www.youtube.com/watch?v=example2",
                "match_date": "2024-02-02"
            }
        ]
    
    # Custom CSS for the slideshow
    st.markdown("""
        <style>
        .highlight-container {
            padding: 20px;
            border-radius: 10px;
            background-color: #f0f2f6;
            margin-bottom: 20px;
        }
        .video-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
            color: #1f77b4;
        }
        .stVideo {
            width: 100%;
            aspect-ratio: 16/9;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Create tabs for navigation between highlights
    tabs = st.tabs([f"Highlight {i+1}" for i in range(len(highlights))])
    
    for i, (tab, highlight) in enumerate(zip(tabs, highlights)):
        with tab:
            col1, col2 = st.columns([3, 1])
            
            with col1:
                video_id = get_youtube_id(highlight['youtube_url'])
                if video_id:
                    # Embed video player
                    st.markdown(f"""
                        <div class="highlight-container">
                            <div class="video-title">{highlight['title']}</div>
                            <iframe
                                src="https://www.youtube.com/embed/{video_id}"
                                frameborder="0"
                                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                allowfullscreen
                                class="stVideo">
                            </iframe>
                        </div>
                    """, unsafe_allow_html=True)
            
            with col2:
                # Show other match details or related highlights
                st.markdown(f"**Match Date:** {highlight['match_date']}")
                
                # You can add more match details here
                st.markdown("### Related Highlights")
                for j, related in enumerate(highlights):
                    if j != i and j < 3:  # Show up to 3 related highlights
                        st.markdown(f"- {related['title']}")


# Add this function to add highlights through admin panel
def show_highlights_management():
    st.subheader("Manage Match Highlights")
    
    with st.form("add_highlight"):
        title = st.text_input("Match Title")
        youtube_url = st.text_input("YouTube URL")
        match_date = st.date_input("Match Date")
        
        if st.form_submit_button("Add Highlight"):
            conn = get_database_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT INTO match_highlights (title, youtube_url, match_date)
                    VALUES (%s, %s, %s)
                """, (title, youtube_url, match_date))
                
                conn.commit()
                st.success("Highlight added successfully!")
            except Exception as e:
                st.error(f"Error adding highlight: {str(e)}")
            finally:
                cursor.close()
                conn.close()
    
    # Show existing highlights with option to delete
    highlights = get_match_highlights()
    if highlights:
        st.subheader("Existing Highlights")
        for highlight in highlights:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{highlight['title']}** ({highlight['match_date']})")
            with col2:
                if st.button("Delete", key=f"del_{highlight['id']}"):
                    conn = get_database_connection()
                    cursor = conn.cursor()
                    
                    try:
                        cursor.execute("DELETE FROM match_highlights WHERE id = %s", 
                                     (highlight['id'],))
                        conn.commit()
                        st.success("Highlight deleted!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error deleting highlight: {str(e)}")
                    finally:
                        cursor.close()
                        conn.close()


def show_create_team():
    st.title("Create Your Team")

    # Show sidebar navigation
    show_sidebar_navigation()

    update_create_team_page()  # Add AI suggestion feature

    # Check if squad is locked
    lock_until = get_current_squad_lock(st.session_state.user['id'])
    if lock_until and lock_until > datetime.now():
        time_remaining = lock_until - datetime.now()
        hours = int(time_remaining.total_seconds() // 3600)
        minutes = int((time_remaining.total_seconds() % 3600) // 60)
        
        st.warning(f"""
            Your squad is currently locked for {hours} hours and {minutes} minutes.
            You can make changes after the lock period expires.
        """)
        
        # Show current squad in read-only mode
        display_locked_squad()
        
        if st.button("Back to Dashboard"):
            st.session_state.page = 'dashboard'
            st.rerun()
        return
    
    # Initialize session states
    if 'selected_players' not in st.session_state:
        st.session_state.selected_players = {
            'GK': None,
            'DEF': [None] * 4,
            'MID': [None] * 4,
            'FWD': [None] * 2
        }
    if 'total_budget' not in st.session_state:
        st.session_state.total_budget = 100.0
    if 'used_budget' not in st.session_state:
        st.session_state.used_budget = 0.0

    # Helper functions remain the same
    def is_player_selected(player_id):
        selections = [st.session_state.selected_players['GK']]
        selections.extend(st.session_state.selected_players['DEF'])
        selections.extend(st.session_state.selected_players['MID'])
        selections.extend(st.session_state.selected_players['FWD'])
        return player_id in [pid for pid in selections if pid is not None]
    
    def update_budget():
        total = 0.0  # Initialize as float
        if st.session_state.selected_players['GK']:
            player = get_player_by_id(st.session_state.selected_players['GK'])
            if player:
                total += float(player['price'])  # Convert Decimal to float
        for pos in ['DEF', 'MID', 'FWD']:
            for player_id in st.session_state.selected_players[pos]:
                if player_id:
                    player = get_player_by_id(player_id)
                    if player:
                        total += float(player['price'])  # Convert Decimal to float
        st.session_state.used_budget = total

    # Budget Display
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"Budget Remaining: ₹{(st.session_state.total_budget - st.session_state.used_budget):.2f} Cr")
    with col2:
        st.info(f"Budget Used: ₹{st.session_state.used_budget:.2f} Cr")
    
    # Create two columns: one for pitch visualization, one for selection
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Team Formation (4-4-2)")
        
        # Load and modify pitch image
        try:
            pitch_image = Image.open("football_pitch.jpg")
            draw = ImageDraw.Draw(pitch_image)
            
            # Define positions for 4-4-2 formation
            positions = {
                'GK': [(130, 490)],
                'DEF': [(40, 380), (90, 410), (210, 410), (300, 380)],
                'MID': [(30, 230), (90, 290), (240, 290), (300, 230)],
                'FWD': [(100, 130), (220, 130)]
            }
            
            # Function to get player name
            def get_player_name(player_id):
                if player_id:
                    player = get_player_by_id(player_id)
                    if player:
                        return player['name']
                return ""
            
            # Draw players on pitch
            try:
                font = ImageFont.truetype("arial.ttf", 12)
            except IOError:
                font = ImageFont.load_default()
            
            # Draw GK
            if st.session_state.selected_players['GK']:
                name = get_player_name(st.session_state.selected_players['GK'])
                draw.text(positions['GK'][0], name, fill="white", font=font)
            
            # Draw other positions
            for position, coords_list in positions.items():
                if position != 'GK':
                    players = st.session_state.selected_players[position]
                    for idx, coords in enumerate(coords_list):
                        if idx < len(players) and players[idx]:
                            name = get_player_name(players[idx])
                            draw.text(coords, name, fill="white", font=font)
            
            # Display the pitch image
            st.image(pitch_image, use_container_width=True)
            
        except Exception as e:
            st.error(f"Error loading pitch image: {str(e)}")
            st.info("Please ensure 'football_pitch.jpg' exists in your project directory")

    # Rest of the code remains the same...
    with col2:
        st.subheader("Select Players")
        
        # Goalkeeper Selection
        st.markdown("### Goalkeeper")
        gk_players = get_available_players('GK')
        gk_options = ["Select Goalkeeper"] + [f"{p['name']} (₹{float(p['price'])}Cr)" for p in gk_players]
        gk_index = st.selectbox("GK", options=range(len(gk_options)), 
                            format_func=lambda x: gk_options[x])
        if gk_index > 0:
            player = gk_players[gk_index-1]
            if not is_player_selected(player['id']) or st.session_state.selected_players['GK'] == player['id']:
                current_gk_price = 0.0
                if st.session_state.selected_players['GK']:
                    current_player = get_player_by_id(st.session_state.selected_players['GK'])
                    if current_player:
                        current_gk_price = float(current_player['price'])
                new_budget = st.session_state.used_budget - current_gk_price + float(player['price'])
                
                if new_budget <= st.session_state.total_budget:
                    st.session_state.selected_players['GK'] = player['id']
                    update_budget()
                else:
                    st.error("Not enough budget for this player!")
            else:
                st.error("Player already selected!")

        # Position labels
        position_labels = {
            'DEF': ['Left Back', 'Left Center Back', 'Right Center Back', 'Right Back'],
            'MID': ['Left Mid', 'Left Center Mid', 'Right Center Mid', 'Right Mid'],
            'FWD': ['Left Striker', 'Right Striker']
        }

        # Create position selections
        def create_position_selections(position, num_players):
            st.markdown(f"### {position}s")
            players = get_available_players(position)
            options = ["Select Player"] + [f"{p['name']} (₹{float(p['price'])}Cr)" for p in players]
            
            for i in range(num_players):
                label = position_labels[position][i]
                idx = st.selectbox(
                    f"{label}", 
                    options=range(len(options)),
                    format_func=lambda x: options[x],
                    key=f"{position}_{i}"
                )
                
                if idx > 0:
                    player = players[idx-1]
                    current_selected = st.session_state.selected_players[position][i]
                    if not is_player_selected(player['id']) or current_selected == player['id']:
                        current_price = 0.0
                        if current_selected:
                            current_player = get_player_by_id(current_selected)
                            if current_player:
                                current_price = float(current_player['price'])
                        new_budget = st.session_state.used_budget - current_price + float(player['price'])
                        
                        if new_budget <= st.session_state.total_budget:
                            st.session_state.selected_players[position][i] = player['id']
                            update_budget()
                        else:
                            st.error("Not enough budget for this player!")
                    else:
                        st.error("Player already selected in another position!")

        # Create selections for each position
        create_position_selections('DEF', 4)
        create_position_selections('MID', 4)
        create_position_selections('FWD', 2)

        # Save and Back buttons
        if st.button("Save Team"):
            all_selected = (
                st.session_state.selected_players['GK'] is not None and
                all(x is not None for x in st.session_state.selected_players['DEF']) and
                all(x is not None for x in st.session_state.selected_players['MID']) and
                all(x is not None for x in st.session_state.selected_players['FWD'])
            )
            
            if all_selected:
                if st.session_state.used_budget <= st.session_state.total_budget:
                    selected_list = (
                        [st.session_state.selected_players['GK']] +
                        st.session_state.selected_players['DEF'] +
                        st.session_state.selected_players['MID'] +
                        st.session_state.selected_players['FWD']
                    )
                    
                    success, result = save_squad_history(st.session_state.user['id'], selected_list)
                    if success:
                        st.success("""
                            Team saved successfully! 
                            Your squad is now locked for 24 hours.
                        """)
                        st.session_state.page = 'dashboard'
                        st.rerun()
                    else:
                        st.error(f"Error saving team: {result}")
                else:
                    st.error("Team exceeds budget limit!")
            else:
                st.error("Please select all required positions before saving")


def display_locked_squad():
    # Get the most recent squad
    conn = get_database_connection()
    cursor = conn.cursor(DictCursor)
    
    cursor.execute("""
        SELECT p.*, sp.position_order
        FROM squad_history sh
        JOIN squad_players sp ON sh.id = sp.squad_id
        JOIN players p ON sp.player_id = p.id
        WHERE sh.user_id = %s
        AND sh.created_at = (
            SELECT MAX(created_at)
            FROM squad_history
            WHERE user_id = %s
        )
        ORDER BY sp.position_order
    """, (st.session_state.user['id'], st.session_state.user['id']))
    
    players = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not players:
        st.error("No saved squad found")
        return
    
    # Display squad using the same visualization as create_team
    try:
        pitch_image = Image.open("football_pitch.jpg")
        draw = ImageDraw.Draw(pitch_image)
        
        positions = {
            'GK': [(130, 490)],
            'DEF': [(40, 380), (90, 410), (210, 410), (300, 380)],
            'MID': [(30, 230), (90, 290), (240, 290), (300, 230)],
            'FWD': [(100, 130), (220, 130)]
        }
        
        try:
            font = ImageFont.truetype("arial.ttf", 12)
        except IOError:
            font = ImageFont.load_default()
        
        # Draw players on pitch based on position_order
        for player in players:
            pos_order = player['position_order']
            if pos_order == 0:  # Goalkeeper
                draw.text(positions['GK'][0], player['name'], fill="white", font=font)
            elif pos_order <= 4:  # Defenders
                draw.text(positions['DEF'][pos_order-1], player['name'], fill="white", font=font)
            elif pos_order <= 8:  # Midfielders
                draw.text(positions['MID'][pos_order-5], player['name'], fill="white", font=font)
            else:  # Forwards
                draw.text(positions['FWD'][pos_order-9], player['name'], fill="white", font=font)
        
        st.image(pitch_image, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error displaying squad: {str(e)}")

# Add a new section to the dashboard to show squad history
def show_squad_history():
    st.header("Squad History")
    history = get_user_squad_history(st.session_state.user['id'])
    
    if not history:
        st.info("No squad history available yet")
        return
    
    for squad in history:
        with st.expander(f"Squad from {squad['created_at'].strftime('%Y-%m-%d %H:%M')}"):
            st.write(f"Total Points: {squad['total_points']}")
            players = zip(
                squad['player_names'].split(','),
                squad['player_points'].split(',')
            )
            for player_name, points in players:
                st.write(f"{player_name}: {points} pts")

# Dashboard page with fixed image handling
def show_dashboard():
    st.title(f"Welcome, {st.session_state.user['username']}!")

    # Show sidebar navigation
    show_sidebar_navigation()

    # Debug prints
    print(f"Current user: {st.session_state.user['username']}")
    print(f"Is admin check: {is_admin(st.session_state.user['username'])}")
    

    if is_admin(st.session_state.user['username']):
        if st.button("🔐 Access Admin Panel", type="primary"):
            st.session_state.page = 'admin'
            st.rerun()
    
    # User Points
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown(
            f"""
            <div style="text-align: center; padding: 20px; background-color: #f0f2f6; border-radius: 10px;">
                <h2 style="color: #1f77b4;">Your Total Points</h2>
                <h1 style="color: #2ecc71;">{st.session_state.user['points']} pts</h1>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    # Leaderboard
    st.header("Leaderboard")
    leaderboard = get_leaderboard()
    if leaderboard:
        df = pd.DataFrame(leaderboard)
        df.index = range(1, len(df) + 1)  # Add ranking
        st.table(df)
    else:
        st.info("No leaderboard data available yet")

    # Add visualizations
    add_dashboard_visualizations()
    
    # Upcoming Matches
    st.header("Upcoming Matches")
    matches = get_upcoming_matches()
    if matches:
        for match in matches:
            col1, col2, col3 = st.columns([2,1,2])
            
            with col1:
                home_logo = load_team_logo(match['home_team'])
                if home_logo:
                    st.image(home_logo, width=50)
                st.write(match['home_team'])
            
            with col2:
                st.write("VS")
                st.write(match['match_time'].strftime("%Y-%m-%d %H:%M"))
            
            with col3:
                away_logo = load_team_logo(match['away_team'])
                if away_logo:
                    st.image(away_logo, width=50)
                st.write(match['away_team'])
    else:
        st.info("No upcoming matches scheduled")
    
    # Replace the old highlights section with the new one
    show_highlights_section()
    
    show_squad_history()
    

def show_admin_page():
    st.title("Admin Dashboard")


    # Show sidebar navigation
    show_sidebar_navigation()
    
    if not st.session_state.user or not is_admin(st.session_state.user['username']):
        st.error("Access denied. Admin privileges required.")
        return
    
    # Add tabs for different admin functions
    admin_tabs = st.tabs(["Match Points", "Highlights Management","Upcoming Matches"])

    with admin_tabs[0]:
        # Your existing match points code
        

        # Match date selection
        match_date = st.date_input("Select Match Date")
        
        matches = get_matches_for_date(match_date)
        if not matches:
            st.warning("No matches found for selected date")
            return
        
        # Match selection
        selected_match = st.selectbox(
            "Select Match",
            matches,
            format_func=lambda x: f"{x['home_team']} vs {x['away_team']}"
        )
        
        if selected_match:
            with st.form("match_result_form"):
                st.subheader("Match Result")
                col1, col2 = st.columns(2)
                
                with col1:
                    home_score = st.number_input(f"{selected_match['home_team']} Score", min_value=0)
                    home_players = get_team_players(selected_match['home_team'])
                    
                    st.subheader(f"{selected_match['home_team']} Players")
                    
                    # Goal scorers and assists for home team
                    home_scorers = st.multiselect(
                        "Goal Scorers",
                        options=[p['name'] for p in home_players],
                        key="home_scorers"
                    )
                    
                    home_assists = st.multiselect(
                        "Assist Providers",
                        options=[p['name'] for p in home_players],
                        key="home_assists"
                    )
                    
                    # Cards for home team
                    home_yellows = st.multiselect(
                        "Yellow Cards",
                        options=[p['name'] for p in home_players],
                        key="home_yellows"
                    )
                    
                    home_reds = st.multiselect(
                        "Red Cards",
                        options=[p['name'] for p in home_players],
                        key="home_reds"
                    )
                
                with col2:
                    away_score = st.number_input(f"{selected_match['away_team']} Score", min_value=0)
                    away_players = get_team_players(selected_match['away_team'])
                    
                    st.subheader(f"{selected_match['away_team']} Players")
                    
                    # Goal scorers and assists for away team
                    away_scorers = st.multiselect(
                        "Goal Scorers",
                        options=[p['name'] for p in away_players],
                        key="away_scorers"
                    )
                    
                    away_assists = st.multiselect(
                        "Assist Providers",
                        options=[p['name'] for p in away_players],
                        key="away_assists"
                    )
                    
                    # Cards for away team
                    away_yellows = st.multiselect(
                        "Yellow Cards",
                        options=[p['name'] for p in away_players],
                        key="away_yellows"
                    )
                    
                    away_reds = st.multiselect(
                        "Red Cards",
                        options=[p['name'] for p in away_players],
                        key="away_reds"
                    )
                
                submit = st.form_submit_button("Submit Match Result")
                
                if submit:
                    try:
                        # Record match result
                        record_match_result(selected_match['id'], home_score, away_score)
                        
                        # Process clean sheets (if applicable)
                        if home_score == 0:
                            # Away team clean sheet
                            for player in away_players:
                                if player['position'] == 'GK':
                                    update_player_points(player['id'], 4)
                                elif player['position'] == 'DEF':
                                    update_player_points(player['id'], 3)
                        
                        if away_score == 0:
                            # Home team clean sheet
                            for player in home_players:
                                if player['position'] == 'GK':
                                    update_player_points(player['id'], 4)
                                elif player['position'] == 'DEF':
                                    update_player_points(player['id'], 3)
                        
                        # Process goals and assists
                        for scorer in home_scorers + away_scorers:
                            player = next((p for p in home_players + away_players if p['name'] == scorer), None)
                            if player:
                                update_player_points(player['id'], 5)
                        
                        for assist in home_assists + away_assists:
                            player = next((p for p in home_players + away_players if p['name'] == assist), None)
                            if player:
                                update_player_points(player['id'], 2)
                        
                        # Process cards
                        for yellow in home_yellows + away_yellows:
                            player = next((p for p in home_players + away_players if p['name'] == yellow), None)
                            if player:
                                update_player_points(player['id'], -3)
                        
                        for red in home_reds + away_reds:
                            player = next((p for p in home_players + away_players if p['name'] == red), None)
                            if player:
                                update_player_points(player['id'], -5)
                        
                        # Add default points for all other players
                        for player in home_players + away_players:
                            if (player['name'] not in home_scorers + away_scorers + 
                                home_assists + away_assists + 
                                home_yellows + away_yellows + 
                                home_reds + away_reds):
                                update_player_points(player['id'], 2)
                        
                        st.info("Processing user points updates...")  # Add status message
                        
                        # Update user points after all player points are updated
                        if update_user_points():
                            st.success("Match result and points updated successfully!")
                        else:
                            st.warning("""
                                Match result saved but there was an error updating user points.
                                Please check the server logs for details.
                                You may need to manually update user points.
                            """)
                            
                    except Exception as e:
                        import traceback
                        error_details = traceback.format_exc()
                        st.error(f"""
                            Error updating match result: {str(e)}
                            
                            Detailed error:
                            {error_details}
                        """)

    with admin_tabs[1]:
        show_highlights_management()

    with admin_tabs[2]:
        st.subheader("Add Upcoming Match")
        isl_teams = ["Mohun Bagan Super Giants", "Bengaluru FC", "Chennaiyin FC", "East Bengal FC", "FC Goa", "Hyderabad FC", "Jamshedpur FC", "Kerala Blasters FC", "Mumbai City FC", "NorthEast United FC", "Odisha FC", "Punjab FC"]
        with st.form("upcoming_match_form"):
            home_team = st.selectbox("Home Team", isl_teams)
            away_team = st.selectbox("Away Team", [team for team in isl_teams if team != home_team])
            match_date = st.date_input("Match Date")
            match_time = st.time_input("Match Time")
            status = "upcoming"
            submit_match = st.form_submit_button("Add Match")
            
            if submit_match:
                try:
                    conn = get_database_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT MAX(id) FROM matches")
                    max_id = cursor.fetchone()[0] or 35
                    new_id = max_id + 1
                    
                    query = """
                        INSERT INTO matches (id, home_team, away_team, match_time, home_logo, away_logo, status, home_score, away_score)
                        VALUES (%s, %s, %s, %s, NULL, NULL, %s, NULL, NULL)
                    """
                    cursor.execute(query, (new_id, home_team, away_team, f"{match_date} {match_time}", status))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    
                    st.success("Upcoming match added successfully!")
                except Exception as e:
                    st.error(f"Error adding match: {str(e)}")
    

# Session state initialization
def init_session_state():
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'page' not in st.session_state:
        st.session_state.page = 'login'

# Login and Register pages remain the same
def show_login_page():
    st.title("ISL Fantasy League")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            user = login_user(username, password)
            if user:
                st.session_state.user = user
                st.session_state.page = 'dashboard'
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    if st.button("New user? Register here"):
        st.session_state.page = 'register'

def show_register_page():
    st.title("Register New Account")
    
    with st.form("register_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submit = st.form_submit_button("Register")
        
        if submit:
            if password != confirm_password:
                st.error("Passwords do not match")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters long")
            else:
                if register_user(username, password):
                    st.success("Registration successful! Please login")
                    st.session_state.page = 'login'
                    st.rerun()
    
    if st.button("Already have an account? Login here"):
        st.session_state.page = 'login'

# Create a new Team Analysis page
def show_team_analysis():
    st.title("Team Analysis")

    # Show sidebar navigation
    show_sidebar_navigation()
    
    if not st.session_state.user:
        st.error("Please log in to view team analysis")
        return
    
    # Points History Chart
    st.header("Points History")
    points_history = get_user_points_history(st.session_state.user['id'])
    if points_history:
        df_points = pd.DataFrame(points_history)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_points['matchday'],
            y=df_points['matchday_points'],
            mode='lines+markers',
            name='Points per Matchday'
        ))
        fig.add_trace(go.Scatter(
            x=df_points['matchday'],
            y=df_points['total_points'].cumsum(),
            mode='lines+markers',
            name='Cumulative Points'
        ))
        fig.update_layout(
            title="Points Progress",
            xaxis_title="Matchday",
            yaxis_title="Points"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No points history available yet")
    
    # Team Composition
    st.header("Current Team Composition")
    composition = get_team_composition_stats(st.session_state.user['id'])
    if composition:
        df_comp = pd.DataFrame(composition)
        fig = go.Figure(data=[go.Pie(
            labels=df_comp['team'],
            values=df_comp['player_count'],
            hole=.3
        )])
        fig.update_layout(title="Players by Team")
        st.plotly_chart(fig, use_container_width=True)
    
    # Position Points Distribution
    st.header("Points by Position")
    position_stats = get_position_points_distribution(st.session_state.user['id'])
    if position_stats:
        df_pos = pd.DataFrame(position_stats)
        fig = go.Figure(data=[
            go.Bar(
                x=df_pos['position'],
                y=df_pos['total_points'],
                text=df_pos['total_points'].round(0),
                textposition='auto',
                name='Total Points'
            )
        ])
        fig.add_trace(go.Scatter(
            x=df_pos['position'],
            y=df_pos['avg_points'],
            mode='lines+markers',
            name='Average Points'
        ))
        fig.update_layout(
            title="Points Distribution by Position",
            xaxis_title="Position",
            yaxis_title="Points"
        )
        st.plotly_chart(fig, use_container_width=True)
    

# Main app
def main():
    init_db()
    init_session_state()
    
    if st.session_state.page == 'login':
        show_login_page()
    elif st.session_state.page == 'register':
        show_register_page()
    elif st.session_state.page == 'dashboard':
        if st.session_state.user:
            show_dashboard()
        else:
            st.session_state.page = 'login'
            st.rerun()
    elif st.session_state.page == 'create_team':
        if st.session_state.user:
            show_create_team()
        else:
            st.session_state.page = 'login'
            st.rerun()
    elif st.session_state.page == 'team_analysis':
        if st.session_state.user:
            show_team_analysis()
        else:
            st.session_state.page = 'login'
            st.rerun()
    elif st.session_state.page == 'admin':  # Add this new condition
        if st.session_state.user and is_admin(st.session_state.user['username']):
            show_admin_page()
        else:
            st.error("Access denied. Admin privileges required.")
            st.session_state.page = 'dashboard'
            st.rerun()

if __name__ == "__main__":
    main()
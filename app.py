from flask import Flask, render_template, request, redirect, session, jsonify
import anthropic
import requests
import os
from dotenv import load_dotenv

# ═══════════════════════════════════════════════
#   LOAD ENVIRONMENT VARIABLES
# ═══════════════════════════════════════════════
load_dotenv()

app = Flask(__name__)
app.secret_key = 'moviefinder-secret-key-2024'

TMDB_KEY      = os.getenv('TMDB_API_KEY')
TMDB_BASE     = 'https://api.themoviedb.org/3'
claude_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

# ═══════════════════════════════════════════════
#   GENRE MAP
# ═══════════════════════════════════════════════
GENRES = {
    'Action':    28,
    'Comedy':    35,
    'Horror':    27,
    'Romance':   10749,
    'Sci-Fi':    878,
    'Animation': 16,
    'Thriller':  53,
    'Drama':     18,
    'Fantasy':   14,
    'Crime':     80,
}


# ═══════════════════════════════════════════════
#   HOMEPAGE — Trending Movies
# ═══════════════════════════════════════════════
@app.route('/')
def index():
    try:
        url  = f'{TMDB_BASE}/trending/movie/week?api_key={TMDB_KEY}'
        data = requests.get(url, timeout=10).json().get('results', [])
        featured = data[0] if data else None
        movies   = data[1:19]
        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=featured,
                               watchlist_ids=watchlist_ids,
                               page_title='Trending This Week')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   SEARCH — Claude AI Powered
# ═══════════════════════════════════════════════
@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect('/')
    try:
        # Ask Claude to refine the search query
        message = claude_client.messages.create(
            model='claude-opus-4-6',
            max_tokens=80,
            messages=[{'role': 'user', 'content':
                f"The user wants to find a movie. Their search is: '{query}'. "
                "Reply with ONLY 2-3 clean keyword search terms for TMDB API. "
                "No punctuation. No explanation. Just the keywords."}]
        )
        refined = message.content[0].text.strip()

        url    = f'{TMDB_BASE}/search/movie?api_key={TMDB_KEY}&query={refined}&include_adult=false'
        movies = requests.get(url, timeout=10).json().get('results', [])
        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               query=query,
                               refined=refined,
                               watchlist_ids=watchlist_ids,
                               page_title=f'Search: {query}')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   GENRE PAGE
# ═══════════════════════════════════════════════
@app.route('/genre/<genre_name>')
def genre(genre_name):
    try:
        genre_id = GENRES.get(genre_name)
        if not genre_id:
            return redirect('/')
        url = (f'{TMDB_BASE}/discover/movie?api_key={TMDB_KEY}'
               f'&with_genres={genre_id}&sort_by=popularity.desc'
               f'&include_adult=false&vote_count.gte=100')
        movies = requests.get(url, timeout=10).json().get('results', [])
        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               genre=genre_name,
                               watchlist_ids=watchlist_ids,
                               page_title=f'{genre_name} Movies')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   MOVIE DETAIL PAGE
# ═══════════════════════════════════════════════
@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    try:
        movie_url  = f'{TMDB_BASE}/movie/{movie_id}?api_key={TMDB_KEY}&append_to_response=credits'
        video_url  = f'{TMDB_BASE}/movie/{movie_id}/videos?api_key={TMDB_KEY}'
        similar_url = f'{TMDB_BASE}/movie/{movie_id}/similar?api_key={TMDB_KEY}'

        movie   = requests.get(movie_url,  timeout=10).json()
        videos  = requests.get(video_url,  timeout=10).json().get('results', [])
        similar = requests.get(similar_url, timeout=10).json().get('results', [])[:6]

        trailer = next(
            (v for v in videos if v['type'] == 'Trailer' and v['site'] == 'YouTube'),
            None
        )

        cast = []
        if 'credits' in movie and 'cast' in movie['credits']:
            cast = movie['credits']['cast'][:8]

        watchlist_ids = session.get('watchlist_ids', [])
        in_watchlist  = movie_id in watchlist_ids

        return render_template('movie.html',
                               movie=movie,
                               trailer=trailer,
                               similar=similar,
                               cast=cast,
                               in_watchlist=in_watchlist,
                               watchlist_ids=watchlist_ids)
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   WATCHLIST — Add Movie
# ═══════════════════════════════════════════════
@app.route('/watchlist/add/<int:movie_id>')
def add_watchlist(movie_id):
    if 'watchlist_ids' not in session:
        session['watchlist_ids'] = []
        session['watchlist_movies'] = []

    if movie_id not in session['watchlist_ids']:
        # Fetch movie details to save
        url   = f'{TMDB_BASE}/movie/{movie_id}?api_key={TMDB_KEY}'
        movie = requests.get(url, timeout=10).json()

        session['watchlist_ids'].append(movie_id)
        session['watchlist_movies'].append({
            'id':          movie.get('id'),
            'title':       movie.get('title'),
            'poster_path': movie.get('poster_path'),
            'vote_average':movie.get('vote_average'),
            'release_date':movie.get('release_date', ''),
        })
        session.modified = True

    return redirect(request.referrer or '/')


# ═══════════════════════════════════════════════
#   WATCHLIST — Remove Movie
# ═══════════════════════════════════════════════
@app.route('/watchlist/remove/<int:movie_id>')
def remove_watchlist(movie_id):
    if 'watchlist_ids' in session:
        ids    = session.get('watchlist_ids', [])
        movies = session.get('watchlist_movies', [])
        if movie_id in ids:
            idx = ids.index(movie_id)
            ids.pop(idx)
            movies.pop(idx)
            session['watchlist_ids']    = ids
            session['watchlist_movies'] = movies
            session.modified = True
    return redirect(request.referrer or '/')


# ═══════════════════════════════════════════════
#   WATCHLIST — View Page
# ═══════════════════════════════════════════════
@app.route('/watchlist')
def watchlist():
    movies        = session.get('watchlist_movies', [])
    watchlist_ids = session.get('watchlist_ids', [])
    return render_template('watchlist.html',
                           movies=movies,
                           watchlist_ids=watchlist_ids,
                           page_title='My Watchlist')


# ═══════════════════════════════════════════════
#   TOP RATED PAGE
# ═══════════════════════════════════════════════
@app.route('/top-rated')
def top_rated():
    try:
        url    = f'{TMDB_BASE}/movie/top_rated?api_key={TMDB_KEY}'
        movies = requests.get(url, timeout=10).json().get('results', [])
        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title='Top Rated Movies')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   NOW PLAYING PAGE
# ═══════════════════════════════════════════════
@app.route('/now-playing')
def now_playing():
    try:
        url    = f'{TMDB_BASE}/movie/now_playing?api_key={TMDB_KEY}'
        movies = requests.get(url, timeout=10).json().get('results', [])
        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title='Now Playing')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   UPCOMING PAGE
# ═══════════════════════════════════════════════
@app.route('/upcoming')
def upcoming():
    try:
        url    = f'{TMDB_BASE}/movie/upcoming?api_key={TMDB_KEY}'
        movies = requests.get(url, timeout=10).json().get('results', [])
        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title='Upcoming Movies')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   RUN APP
# ═══════════════════════════════════════════════
if __name__ == '__main__':
    app.run(debug=True)
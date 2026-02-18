from flask import Flask, render_template, request, redirect, session, jsonify, abort
import anthropic
import requests
import os
import random
from datetime import datetime
from dotenv import load_dotenv

# ═══════════════════════════════════════════════
#   LOAD ENVIRONMENT VARIABLES
# ═══════════════════════════════════════════════
load_dotenv()

app = Flask(__name__)
app.secret_key = 'moviefinder-secret-key-2024'

TMDB_KEY  = os.getenv('TMDB_API_KEY')
TMDB_BASE = 'https://api.themoviedb.org/3'
IMG_BASE  = 'https://image.tmdb.org/t/p/w500'
IMG_ORIG  = 'https://image.tmdb.org/t/p/original'

# ═══════════════════════════════════════════════
#   SAFE ANTHROPIC CLIENT INIT
# ═══════════════════════════════════════════════
try:
    claude_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
except Exception:
    claude_client = None

# ═══════════════════════════════════════════════
#   GENRE MAP
# ═══════════════════════════════════════════════
GENRES = {
    'Action':      28,
    'Comedy':      35,
    'Horror':      27,
    'Romance':     10749,
    'Sci-Fi':      878,
    'Animation':   16,
    'Thriller':    53,
    'Drama':       18,
    'Fantasy':     14,
    'Crime':       80,
    'Documentary': 99,
    'Adventure':   12,
    'Mystery':     9648,
    'Music':       10402,
    'History':     36,
    'War':         10752,
    'Western':     37,
    'Family':      10751,
}

# ═══════════════════════════════════════════════
#   MOOD TO GENRE MAP (for Claude AI mood feature)
# ═══════════════════════════════════════════════
MOOD_GENRES = {
    'happy':     ['Comedy', 'Animation', 'Family'],
    'sad':       ['Drama', 'Romance'],
    'excited':   ['Action', 'Adventure', 'Sci-Fi'],
    'scared':    ['Horror', 'Thriller'],
    'romantic':  ['Romance', 'Drama'],
    'bored':     ['Action', 'Crime', 'Mystery'],
    'nostalgic': ['Animation', 'Family', 'History'],
    'curious':   ['Documentary', 'Mystery', 'Sci-Fi'],
    'relaxed':   ['Comedy', 'Music', 'Family'],
    'angry':     ['Action', 'Thriller', 'Crime'],
}

# ═══════════════════════════════════════════════
#   LANGUAGE MAP
# ═══════════════════════════════════════════════
LANGUAGES = {
    'English':    'en',
    'Hindi':      'hi',
    'Spanish':    'es',
    'French':     'fr',
    'Korean':     'ko',
    'Japanese':   'ja',
    'Italian':    'it',
    'German':     'de',
    'Chinese':    'zh',
    'Portuguese': 'pt',
}

# ═══════════════════════════════════════════════
#   HELPER — Safe TMDB Request
# ═══════════════════════════════════════════════
def tmdb_get(url):
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {}
    except requests.exceptions.Timeout:
        return {}
    except requests.exceptions.HTTPError:
        return {}
    except Exception:
        return {}


# ═══════════════════════════════════════════════
#   HELPER — Safe Claude AI Call
# ═══════════════════════════════════════════════
def ask_claude(prompt, max_tokens=200):
    if not claude_client:
        return None
    try:
        message = claude_client.messages.create(
            model='claude-opus-4-6',
            max_tokens=max_tokens,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return message.content[0].text.strip()
    except anthropic.APIConnectionError:
        return None
    except anthropic.APIStatusError:
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════
#   HELPER — Refine Search Query with Claude
# ═══════════════════════════════════════════════
def refine_query_with_claude(query):
    prompt = (
        f"The user wants to find a movie. Their search is: '{query}'. "
        "Reply with ONLY 2-3 clean keyword search terms for TMDB API. "
        "No punctuation. No explanation. Just the keywords."
    )
    refined = ask_claude(prompt, max_tokens=80)
    return refined if refined else query


# ═══════════════════════════════════════════════
#   HELPER — Get AI Movie Review
# ═══════════════════════════════════════════════
def get_ai_review(title, overview, rating, year):
    prompt = (
        f"Write a short, engaging 3-sentence movie review for '{title}' ({year}). "
        f"TMDB Rating: {rating}/10. Overview: {overview}. "
        "Be honest, witty, and helpful. Don't start with 'I'."
    )
    return ask_claude(prompt, max_tokens=200)


# ═══════════════════════════════════════════════
#   HELPER — Get AI Movie Recommendation Reason
# ═══════════════════════════════════════════════
def get_recommendation_reason(title, genre_names, rating):
    prompt = (
        f"In one sentence, explain why someone should watch '{title}' "
        f"(genres: {', '.join(genre_names)}, rating: {rating}/10). "
        "Be enthusiastic and specific. No filler phrases."
    )
    return ask_claude(prompt, max_tokens=80)


# ═══════════════════════════════════════════════
#   HELPER — Get AI Mood Recommendation Message
# ═══════════════════════════════════════════════
def get_mood_message(mood, movies):
    titles = ', '.join([m.get('title', '') for m in movies[:5]])
    prompt = (
        f"The user is feeling '{mood}'. I recommended these movies: {titles}. "
        "Write one warm, fun sentence explaining why these are perfect for their mood."
    )
    return ask_claude(prompt, max_tokens=100)


# ═══════════════════════════════════════════════
#   HELPER — Get AI Fun Fact About Movie
# ═══════════════════════════════════════════════
def get_movie_fun_fact(title, year):
    prompt = (
        f"Give one short, interesting behind-the-scenes fun fact about the movie '{title}' ({year}). "
        "Keep it to 1-2 sentences. If you don't know a specific fact, give a general interesting trivia."
    )
    return ask_claude(prompt, max_tokens=120)


# ═══════════════════════════════════════════════
#   HELPER — Get AI Actor Bio Summary
# ═══════════════════════════════════════════════
def get_actor_summary(name, known_for):
    prompt = (
        f"Write a 2-sentence engaging bio for actor/actress '{name}', "
        f"known for: {known_for}. Make it exciting and highlight their best qualities."
    )
    return ask_claude(prompt, max_tokens=150)


# ═══════════════════════════════════════════════
#   HELPER — Get AI Trivia Quiz Question
# ═══════════════════════════════════════════════
def get_trivia_question(title, year):
    prompt = (
        f"Create a multiple choice trivia question about the movie '{title}' ({year}). "
        "Format your response EXACTLY like this:\n"
        "QUESTION: [question text]\n"
        "A: [option a]\n"
        "B: [option b]\n"
        "C: [option c]\n"
        "D: [option d]\n"
        "ANSWER: [correct letter]\n"
        "FACT: [one interesting fact about the answer]"
    )
    return ask_claude(prompt, max_tokens=200)


# ═══════════════════════════════════════════════
#   HELPER — Format Runtime
# ═══════════════════════════════════════════════
def format_runtime(minutes):
    if not minutes:
        return 'N/A'
    hours = minutes // 60
    mins  = minutes % 60
    return f'{hours}h {mins}m'


# ═══════════════════════════════════════════════
#   HELPER — Format Money
# ═══════════════════════════════════════════════
def format_money(amount):
    if not amount or amount == 0:
        return 'N/A'
    if amount >= 1_000_000_000:
        return f'${amount / 1_000_000_000:.1f}B'
    if amount >= 1_000_000:
        return f'${amount / 1_000_000:.1f}M'
    return f'${amount:,}'


# ═══════════════════════════════════════════════
#   HELPER — Get Year from Date String
# ═══════════════════════════════════════════════
def get_year(date_str):
    try:
        return date_str[:4] if date_str else 'N/A'
    except Exception:
        return 'N/A'


# ═══════════════════════════════════════════════
#   TEMPLATE FILTERS
# ═══════════════════════════════════════════════
@app.template_filter('runtime')
def runtime_filter(minutes):
    return format_runtime(minutes)

@app.template_filter('money')
def money_filter(amount):
    return format_money(amount)

@app.template_filter('year')
def year_filter(date_str):
    return get_year(date_str)

@app.template_filter('stars')
def stars_filter(rating):
    try:
        stars = round(float(rating) / 2)
        return '★' * stars + '☆' * (5 - stars)
    except Exception:
        return '☆☆☆☆☆'


# ═══════════════════════════════════════════════
#   CONTEXT PROCESSOR — Inject globals to all templates
# ═══════════════════════════════════════════════
@app.context_processor
def inject_globals():
    return {
        'genres':       GENRES,
        'languages':    LANGUAGES,
        'moods':        list(MOOD_GENRES.keys()),
        'current_year': datetime.now().year,
        'img_base':     IMG_BASE,
        'img_orig':     IMG_ORIG,
    }


# ═══════════════════════════════════════════════
#   HOMEPAGE — Trending + Popular + Top Picks
# ═══════════════════════════════════════════════
@app.route('/')
def index():
    try:
        trending_url = f'{TMDB_BASE}/trending/movie/week?api_key={TMDB_KEY}'
        popular_url  = f'{TMDB_BASE}/movie/popular?api_key={TMDB_KEY}'
        top_url      = f'{TMDB_BASE}/movie/top_rated?api_key={TMDB_KEY}'

        trending_data = tmdb_get(trending_url).get('results', [])
        popular_data  = tmdb_get(popular_url).get('results', [])
        top_data      = tmdb_get(top_url).get('results', [])

        featured  = trending_data[0] if trending_data else None
        trending  = trending_data[1:13]
        popular   = popular_data[:8]
        top_picks = top_data[:6]

        watchlist_ids = session.get('watchlist_ids', [])

        return render_template('index.html',
                               movies=trending,
                               featured=featured,
                               popular=popular,
                               top_picks=top_picks,
                               watchlist_ids=watchlist_ids,
                               page_title='Trending This Week')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   SEARCH — Claude AI Powered with Filters
# ═══════════════════════════════════════════════
@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    year  = request.args.get('year', '').strip()
    lang  = request.args.get('lang', '').strip()
    sort  = request.args.get('sort', 'popularity.desc').strip()

    if not query:
        return redirect('/')
    try:
        refined = refine_query_with_claude(query)

        url = (f'{TMDB_BASE}/search/movie?api_key={TMDB_KEY}'
               f'&query={refined}&include_adult=false')
        if year:
            url += f'&year={year}'
        if lang:
            url += f'&language={lang}'

        movies = tmdb_get(url).get('results', [])

        # Fallback: if Claude refined gives no results use original query
        if not movies and refined != query:
            fallback_url = (f'{TMDB_BASE}/search/movie?api_key={TMDB_KEY}'
                            f'&query={query}&include_adult=false')
            movies = tmdb_get(fallback_url).get('results', [])

        # Sort results client-side
        if sort == 'vote_average.desc':
            movies = sorted(movies, key=lambda x: x.get('vote_average', 0), reverse=True)
        elif sort == 'release_date.desc':
            movies = sorted(movies, key=lambda x: x.get('release_date', ''), reverse=True)
        elif sort == 'title.asc':
            movies = sorted(movies, key=lambda x: x.get('title', ''))

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
#   GENRE PAGE — With Pagination and Sorting
# ═══════════════════════════════════════════════
@app.route('/genre/<genre_name>')
def genre(genre_name):
    try:
        genre_id = GENRES.get(genre_name)
        if not genre_id:
            return redirect('/')

        page = request.args.get('page', 1, type=int)
        sort = request.args.get('sort', 'popularity.desc')

        url = (f'{TMDB_BASE}/discover/movie?api_key={TMDB_KEY}'
               f'&with_genres={genre_id}&sort_by={sort}'
               f'&include_adult=false&vote_count.gte=100&page={page}')

        data        = tmdb_get(url)
        movies      = data.get('results', [])
        total_pages = min(data.get('total_pages', 1), 10)

        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               genre=genre_name,
                               watchlist_ids=watchlist_ids,
                               page_title=f'{genre_name} Movies',
                               current_page=page,
                               total_pages=total_pages)
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   MOVIE DETAIL PAGE — Full Info + AI Features
# ═══════════════════════════════════════════════
@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    try:
        movie_url   = f'{TMDB_BASE}/movie/{movie_id}?api_key={TMDB_KEY}&append_to_response=credits,keywords,reviews'
        video_url   = f'{TMDB_BASE}/movie/{movie_id}/videos?api_key={TMDB_KEY}'
        similar_url = f'{TMDB_BASE}/movie/{movie_id}/similar?api_key={TMDB_KEY}'
        recom_url   = f'{TMDB_BASE}/movie/{movie_id}/recommendations?api_key={TMDB_KEY}'

        movie       = tmdb_get(movie_url)
        videos      = tmdb_get(video_url).get('results', [])
        similar     = tmdb_get(similar_url).get('results', [])[:6]
        recommended = tmdb_get(recom_url).get('results', [])[:6]

        if not movie or 'id' not in movie:
            return render_template('error.html', error='Movie not found.')

        # Trailer and video clips
        trailer = next(
            (v for v in videos if v.get('type') == 'Trailer' and v.get('site') == 'YouTube'),
            None
        )
        teaser = None
        if not trailer:
            teaser = next(
                (v for v in videos if v.get('type') == 'Teaser' and v.get('site') == 'YouTube'),
                None
            )
        clips = [v for v in videos if v.get('site') == 'YouTube'][:5]

        # Cast and crew
        cast     = []
        director = None
        writers  = []

        if 'credits' in movie:
            cast          = movie['credits'].get('cast', [])[:12]
            crew          = movie['credits'].get('crew', [])
            director_list = [c for c in crew if c.get('job') == 'Director']
            director      = director_list[0] if director_list else None
            writers       = [c for c in crew if c.get('job') in ['Writer', 'Screenplay', 'Story']][:3]

        # Keywords
        keywords = []
        if 'keywords' in movie:
            keywords = movie['keywords'].get('keywords', [])[:10]

        # Reviews
        reviews = []
        if 'reviews' in movie:
            reviews = movie['reviews'].get('results', [])[:3]

        # Genre names for AI
        genre_names = [g['name'] for g in movie.get('genres', [])]

        # AI Features
        title    = movie.get('title', '')
        overview = movie.get('overview', '')
        rating   = movie.get('vote_average', 0)
        year     = get_year(movie.get('release_date', ''))

        ai_review   = get_ai_review(title, overview, rating, year)
        ai_fun_fact = get_movie_fun_fact(title, year)

        # Production info
        companies        = movie.get('production_companies', [])[:4]
        spoken_languages = movie.get('spoken_languages', [])

        # Collection / franchise
        belongs_to_collection = movie.get('belongs_to_collection')

        watchlist_ids = session.get('watchlist_ids', [])
        in_watchlist  = movie_id in watchlist_ids

        return render_template('movie.html',
                               movie=movie,
                               trailer=trailer,
                               teaser=teaser,
                               clips=clips,
                               similar=similar,
                               recommended=recommended,
                               cast=cast,
                               director=director,
                               writers=writers,
                               keywords=keywords,
                               reviews=reviews,
                               genre_names=genre_names,
                               companies=companies,
                               spoken_languages=spoken_languages,
                               belongs_to_collection=belongs_to_collection,
                               ai_review=ai_review,
                               ai_fun_fact=ai_fun_fact,
                               in_watchlist=in_watchlist,
                               watchlist_ids=watchlist_ids,
                               format_runtime=format_runtime,
                               format_money=format_money)
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   ACTOR / PERSON DETAIL PAGE
# ═══════════════════════════════════════════════
@app.route('/actor/<int:person_id>')
def actor_detail(person_id):
    try:
        person_url = f'{TMDB_BASE}/person/{person_id}?api_key={TMDB_KEY}&append_to_response=movie_credits,images'
        person     = tmdb_get(person_url)

        if not person or 'id' not in person:
            return render_template('error.html', error='Person not found.')

        movies = sorted(
            person.get('movie_credits', {}).get('cast', []),
            key=lambda x: x.get('popularity', 0),
            reverse=True
        )[:20]

        directed = sorted(
            [m for m in person.get('movie_credits', {}).get('crew', []) if m.get('job') == 'Director'],
            key=lambda x: x.get('popularity', 0),
            reverse=True
        )[:10]

        images           = person.get('images', {}).get('profiles', [])[:8]
        known_for_titles = ', '.join([m.get('title', '') for m in movies[:3]])
        ai_bio           = get_actor_summary(person.get('name', ''), known_for_titles)

        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('actor.html',
                               person=person,
                               movies=movies,
                               directed=directed,
                               images=images,
                               ai_bio=ai_bio,
                               watchlist_ids=watchlist_ids,
                               page_title=person.get('name', 'Actor'))
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   MOOD PAGE — Choose your Mood
# ═══════════════════════════════════════════════
@app.route('/mood')
def mood_page():
    watchlist_ids = session.get('watchlist_ids', [])
    return render_template('mood.html',
                           moods=list(MOOD_GENRES.keys()),
                           watchlist_ids=watchlist_ids,
                           page_title='Movie by Mood')


# ═══════════════════════════════════════════════
#   MOOD MOVIES — Recommended by Mood
# ═══════════════════════════════════════════════
@app.route('/mood/<mood_name>')
def mood_movies(mood_name):
    try:
        mood_name  = mood_name.lower()
        genre_list = MOOD_GENRES.get(mood_name, ['Action'])
        genre_ids  = [str(GENRES.get(g, '')) for g in genre_list if g in GENRES]
        genre_str  = '|'.join(genre_ids)

        url = (f'{TMDB_BASE}/discover/movie?api_key={TMDB_KEY}'
               f'&with_genres={genre_str}&sort_by=popularity.desc'
               f'&include_adult=false&vote_count.gte=200')

        movies = tmdb_get(url).get('results', [])
        random.shuffle(movies)
        movies = movies[:12]

        mood_message  = get_mood_message(mood_name, movies)
        watchlist_ids = session.get('watchlist_ids', [])

        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               mood=mood_name,
                               mood_message=mood_message,
                               page_title=f'Feeling {mood_name.capitalize()}? Watch These!')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   LANGUAGE FILTER PAGE
# ═══════════════════════════════════════════════
@app.route('/language/<lang_name>')
def language_movies(lang_name):
    try:
        lang_code = LANGUAGES.get(lang_name)
        if not lang_code:
            return redirect('/')

        url = (f'{TMDB_BASE}/discover/movie?api_key={TMDB_KEY}'
               f'&with_original_language={lang_code}'
               f'&sort_by=popularity.desc&include_adult=false'
               f'&vote_count.gte=100')

        movies        = tmdb_get(url).get('results', [])
        watchlist_ids = session.get('watchlist_ids', [])

        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title=f'{lang_name} Movies')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   TOP RATED PAGE — With Pagination
# ═══════════════════════════════════════════════
@app.route('/top-rated')
def top_rated():
    try:
        page        = request.args.get('page', 1, type=int)
        url         = f'{TMDB_BASE}/movie/top_rated?api_key={TMDB_KEY}&page={page}'
        data        = tmdb_get(url)
        movies      = data.get('results', [])
        total_pages = min(data.get('total_pages', 1), 10)

        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title='Top Rated Movies',
                               current_page=page,
                               total_pages=total_pages)
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   NOW PLAYING PAGE — With Pagination
# ═══════════════════════════════════════════════
@app.route('/now-playing')
def now_playing():
    try:
        page        = request.args.get('page', 1, type=int)
        url         = f'{TMDB_BASE}/movie/now_playing?api_key={TMDB_KEY}&page={page}'
        data        = tmdb_get(url)
        movies      = data.get('results', [])
        total_pages = min(data.get('total_pages', 1), 5)

        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title='Now Playing',
                               current_page=page,
                               total_pages=total_pages)
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   UPCOMING PAGE — With Pagination
# ═══════════════════════════════════════════════
@app.route('/upcoming')
def upcoming():
    try:
        page        = request.args.get('page', 1, type=int)
        url         = f'{TMDB_BASE}/movie/upcoming?api_key={TMDB_KEY}&page={page}'
        data        = tmdb_get(url)
        movies      = data.get('results', [])
        total_pages = min(data.get('total_pages', 1), 5)

        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title='Upcoming Movies',
                               current_page=page,
                               total_pages=total_pages)
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   POPULAR PAGE — With Pagination
# ═══════════════════════════════════════════════
@app.route('/popular')
def popular():
    try:
        page        = request.args.get('page', 1, type=int)
        url         = f'{TMDB_BASE}/movie/popular?api_key={TMDB_KEY}&page={page}'
        data        = tmdb_get(url)
        movies      = data.get('results', [])
        total_pages = min(data.get('total_pages', 1), 10)

        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title='Popular Movies',
                               current_page=page,
                               total_pages=total_pages)
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   DECADE FILTER PAGE
# ═══════════════════════════════════════════════
@app.route('/decade/<int:decade>')
def decade_movies(decade):
    try:
        valid_decades = [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
        if decade not in valid_decades:
            return redirect('/')

        start_year = decade
        end_year   = decade + 9

        url = (f'{TMDB_BASE}/discover/movie?api_key={TMDB_KEY}'
               f'&primary_release_date.gte={start_year}-01-01'
               f'&primary_release_date.lte={end_year}-12-31'
               f'&sort_by=popularity.desc&include_adult=false'
               f'&vote_count.gte=100')

        movies        = tmdb_get(url).get('results', [])
        watchlist_ids = session.get('watchlist_ids', [])

        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title=f'{decade}s Movies')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   COLLECTION / FRANCHISE PAGE
# ═══════════════════════════════════════════════
@app.route('/collection/<int:collection_id>')
def collection(collection_id):
    try:
        url        = f'{TMDB_BASE}/collection/{collection_id}?api_key={TMDB_KEY}'
        col_data   = tmdb_get(url)

        if not col_data or 'id' not in col_data:
            return redirect('/')

        movies = sorted(
            col_data.get('parts', []),
            key=lambda x: x.get('release_date', ''),
        )

        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('index.html',
                               movies=movies,
                               featured=None,
                               watchlist_ids=watchlist_ids,
                               page_title=col_data.get('name', 'Collection'))
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   WATCHLIST — Add Movie
# ═══════════════════════════════════════════════
@app.route('/watchlist/add/<int:movie_id>')
def add_watchlist(movie_id):
    if 'watchlist_ids' not in session:
        session['watchlist_ids']    = []
        session['watchlist_movies'] = []

    if movie_id not in session['watchlist_ids']:
        url   = f'{TMDB_BASE}/movie/{movie_id}?api_key={TMDB_KEY}'
        movie = tmdb_get(url)

        if movie and 'id' in movie:
            session['watchlist_ids'].append(movie_id)
            session['watchlist_movies'].append({
                'id':           movie.get('id'),
                'title':        movie.get('title'),
                'poster_path':  movie.get('poster_path'),
                'vote_average': movie.get('vote_average'),
                'release_date': movie.get('release_date', ''),
                'overview':     movie.get('overview', ''),
                'genre_ids':    [g['id'] for g in movie.get('genres', [])],
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
#   WATCHLIST — View Page with Sort
# ═══════════════════════════════════════════════
@app.route('/watchlist')
def watchlist():
    movies        = session.get('watchlist_movies', [])
    watchlist_ids = session.get('watchlist_ids', [])
    sort          = request.args.get('sort', 'added')

    if sort == 'rating':
        movies = sorted(movies, key=lambda x: x.get('vote_average', 0), reverse=True)
    elif sort == 'title':
        movies = sorted(movies, key=lambda x: x.get('title', ''))
    elif sort == 'year':
        movies = sorted(movies, key=lambda x: x.get('release_date', ''), reverse=True)

    return render_template('watchlist.html',
                           movies=movies,
                           watchlist_ids=watchlist_ids,
                           page_title='My Watchlist',
                           sort=sort)


# ═══════════════════════════════════════════════
#   WATCHLIST — Clear All
# ═══════════════════════════════════════════════
@app.route('/watchlist/clear')
def clear_watchlist():
    session['watchlist_ids']    = []
    session['watchlist_movies'] = []
    session.modified = True
    return redirect('/watchlist')


# ═══════════════════════════════════════════════
#   API — Watchlist as JSON
# ═══════════════════════════════════════════════
@app.route('/api/watchlist')
def api_watchlist():
    movies = session.get('watchlist_movies', [])
    return jsonify({'count': len(movies), 'movies': movies})


# ═══════════════════════════════════════════════
#   API — Movie Details as JSON
# ═══════════════════════════════════════════════
@app.route('/api/movie/<int:movie_id>')
def api_movie(movie_id):
    url   = f'{TMDB_BASE}/movie/{movie_id}?api_key={TMDB_KEY}'
    movie = tmdb_get(url)
    if not movie or 'id' not in movie:
        return jsonify({'error': 'Movie not found'}), 404
    return jsonify(movie)


# ═══════════════════════════════════════════════
#   API — Search as JSON
# ═══════════════════════════════════════════════
@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    url    = f'{TMDB_BASE}/search/movie?api_key={TMDB_KEY}&query={query}&include_adult=false'
    movies = tmdb_get(url).get('results', [])
    return jsonify({'query': query, 'count': len(movies), 'results': movies})


# ═══════════════════════════════════════════════
#   API — AI Review as JSON
# ═══════════════════════════════════════════════
@app.route('/api/review/<int:movie_id>')
def api_review(movie_id):
    url   = f'{TMDB_BASE}/movie/{movie_id}?api_key={TMDB_KEY}'
    movie = tmdb_get(url)
    if not movie or 'id' not in movie:
        return jsonify({'error': 'Movie not found'}), 404
    title    = movie.get('title', '')
    overview = movie.get('overview', '')
    rating   = movie.get('vote_average', 0)
    year     = get_year(movie.get('release_date', ''))
    review   = get_ai_review(title, overview, rating, year)
    return jsonify({'movie': title, 'review': review})


# ═══════════════════════════════════════════════
#   API — AI Trivia as JSON
# ═══════════════════════════════════════════════
@app.route('/api/trivia/<int:movie_id>')
def api_trivia(movie_id):
    url   = f'{TMDB_BASE}/movie/{movie_id}?api_key={TMDB_KEY}'
    movie = tmdb_get(url)
    if not movie or 'id' not in movie:
        return jsonify({'error': 'Movie not found'}), 404
    title  = movie.get('title', '')
    year   = get_year(movie.get('release_date', ''))
    trivia = get_trivia_question(title, year)
    return jsonify({'movie': title, 'trivia': trivia})


# ═══════════════════════════════════════════════
#   API — Trending as JSON
# ═══════════════════════════════════════════════
@app.route('/api/trending')
def api_trending():
    url    = f'{TMDB_BASE}/trending/movie/week?api_key={TMDB_KEY}'
    movies = tmdb_get(url).get('results', [])
    return jsonify({'count': len(movies), 'results': movies})


# ═══════════════════════════════════════════════
#   API — Recommendations as JSON
# ═══════════════════════════════════════════════
@app.route('/api/recommendations/<int:movie_id>')
def api_recommendations(movie_id):
    url    = f'{TMDB_BASE}/movie/{movie_id}/recommendations?api_key={TMDB_KEY}'
    movies = tmdb_get(url).get('results', [])
    return jsonify({'movie_id': movie_id, 'count': len(movies), 'results': movies})


# ═══════════════════════════════════════════════
#   API — Similar Movies as JSON
# ═══════════════════════════════════════════════
@app.route('/api/similar/<int:movie_id>')
def api_similar(movie_id):
    url    = f'{TMDB_BASE}/movie/{movie_id}/similar?api_key={TMDB_KEY}'
    movies = tmdb_get(url).get('results', [])
    return jsonify({'movie_id': movie_id, 'count': len(movies), 'results': movies})


# ═══════════════════════════════════════════════
#   API — Actor Info as JSON
# ═══════════════════════════════════════════════
@app.route('/api/actor/<int:person_id>')
def api_actor(person_id):
    url    = f'{TMDB_BASE}/person/{person_id}?api_key={TMDB_KEY}&append_to_response=movie_credits'
    person = tmdb_get(url)
    if not person or 'id' not in person:
        return jsonify({'error': 'Person not found'}), 404
    return jsonify(person)


# ═══════════════════════════════════════════════
#   API — Genre Movies as JSON
# ═══════════════════════════════════════════════
@app.route('/api/genre/<genre_name>')
def api_genre(genre_name):
    genre_id = GENRES.get(genre_name)
    if not genre_id:
        return jsonify({'error': 'Genre not found'}), 404
    url    = (f'{TMDB_BASE}/discover/movie?api_key={TMDB_KEY}'
              f'&with_genres={genre_id}&sort_by=popularity.desc'
              f'&include_adult=false&vote_count.gte=100')
    movies = tmdb_get(url).get('results', [])
    return jsonify({'genre': genre_name, 'count': len(movies), 'results': movies})


# ═══════════════════════════════════════════════
#   TRIVIA GAME PAGE
# ═══════════════════════════════════════════════
@app.route('/trivia')
def trivia_page():
    try:
        url    = f'{TMDB_BASE}/movie/popular?api_key={TMDB_KEY}'
        movies = tmdb_get(url).get('results', [])

        if not movies:
            return render_template('error.html', error='Could not load trivia.')

        movie  = random.choice(movies[:15])
        title  = movie.get('title', '')
        year   = get_year(movie.get('release_date', ''))
        trivia = get_trivia_question(title, year)

        watchlist_ids = session.get('watchlist_ids', [])
        return render_template('trivia.html',
                               movie=movie,
                               trivia=trivia,
                               watchlist_ids=watchlist_ids,
                               page_title='Movie Trivia')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   RANDOM MOVIE PICKER
# ═══════════════════════════════════════════════
@app.route('/random')
def random_movie():
    try:
        genre_name = request.args.get('genre', '')
        page       = random.randint(1, 5)

        if genre_name and genre_name in GENRES:
            genre_id = GENRES[genre_name]
            url = (f'{TMDB_BASE}/discover/movie?api_key={TMDB_KEY}'
                   f'&with_genres={genre_id}&sort_by=popularity.desc'
                   f'&include_adult=false&vote_count.gte=200&page={page}')
        else:
            url = f'{TMDB_BASE}/movie/popular?api_key={TMDB_KEY}&page={page}'

        movies = tmdb_get(url).get('results', [])
        if not movies:
            return redirect('/')

        movie = random.choice(movies)
        return redirect(f'/movie/{movie["id"]}')
    except Exception as e:
        return render_template('error.html', error=str(e))


# ═══════════════════════════════════════════════
#   ABOUT PAGE
# ═══════════════════════════════════════════════
@app.route('/about')
def about():
    watchlist_ids = session.get('watchlist_ids', [])
    return render_template('about.html',
                           watchlist_ids=watchlist_ids,
                           page_title='About MovieProfix')


# ═══════════════════════════════════════════════
#   TEST ROUTE — DELETE AFTER FIXING
# ═══════════════════════════════════════════════
@app.route('/test')
def test():
    url = f'{TMDB_BASE}/trending/movie/week?api_key={TMDB_KEY}'
    data = tmdb_get(url)
    movies = data.get('results', [])
    return jsonify({
        'tmdb_key_set': bool(TMDB_KEY),
        'tmdb_key_value': TMDB_KEY[:6] + '...' if TMDB_KEY else 'MISSING',
        'movies_count': len(movies),
        'first_movie': movies[0].get('title') if movies else 'None',
    })


# ═══════════════════════════════════════════════
#   404 ERROR HANDLER
# ═══════════════════════════════════════════════
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error='Page not found (404).'), 404


# ═══════════════════════════════════════════════
#   500 ERROR HANDLER
# ═══════════════════════════════════════════════
@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error='Server error (500). Please try again.'), 500


# ═══════════════════════════════════════════════
#   RUN APP
# ═══════════════════════════════════════════════
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
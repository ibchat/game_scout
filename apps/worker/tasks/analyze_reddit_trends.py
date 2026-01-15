from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_investor import YouTubeTrendSnapshot
from apps.db.models_youtube import RedditTrendPost
from datetime import date, timedelta
import logging
from collections import Counter
import re

logger = logging.getLogger(__name__)

@celery_app.task(name="analyze_reddit_trends")
def analyze_reddit_trends_task(query_set='indie_radar'):
    db = get_db_session()
    try:
        today = date.today()
        
        # Глубокий парсинг - последние 7 дней для трендового анализа
        week_ago = today - timedelta(days=7)
        
        posts_today = db.query(RedditTrendPost).filter(
            RedditTrendPost.query_set == query_set,
            RedditTrendPost.collected_at >= today
        ).order_by(RedditTrendPost.score.desc()).all()
        
        posts_week = db.query(RedditTrendPost).filter(
            RedditTrendPost.query_set == query_set,
            RedditTrendPost.collected_at >= week_ago
        ).order_by(RedditTrendPost.score.desc()).all()
        
        if not posts_today:
            return {"status": "no_data"}
        
        # ГЛУБОКИЙ АНАЛИЗ
        analysis = deep_analyze_posts(posts_today, posts_week)
        
        # Генерация детальных рекомендаций
        recommendations = generate_detailed_recommendations(analysis)
        
        # Сохранить snapshot
        snapshot = YouTubeTrendSnapshot(
            date=today,
            query_set=f"reddit_{query_set}",
            top_terms=analysis['top_terms'],
            top_patterns=analysis['trending_patterns'],
            top_mechanics=analysis['top_mechanics'],
            top_games_mentions=analysis['mentioned_games'],
            signals={
                'total_score': analysis['total_score'],
                'total_comments': analysis['total_comments'],
                'avg_upvote_ratio': analysis['avg_upvote_ratio'],
                'community_sentiment': analysis['sentiment'],
                'recommendations_ru': recommendations,
                'growth_rate': analysis['growth_rate'],
                'viral_posts': analysis['viral_posts'],
                'emerging_mechanics': analysis['emerging_mechanics'],
                'investment_signals': analysis['investment_signals']
            },
            confidence=0.85,
            video_count=len(posts_today)
        )
        db.merge(snapshot)
        db.commit()
        
        logger.info(f"Deep analyzed {len(posts_today)} Reddit posts")
        return {"status": "success", "posts": len(posts_today)}
        
    except Exception as e:
        logger.error(f"Reddit analysis error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()

def deep_analyze_posts(posts_today, posts_week):
    """Глубокий анализ трендов"""
    
    # Базовые метрики
    total_score = sum(p.score or 0 for p in posts_today)
    total_comments = sum(p.num_comments or 0 for p in posts_today)
    avg_ratio = sum(p.upvote_ratio or 0 for p in posts_today) / len(posts_today) if posts_today else 0
    
    # Рост метрик (сегодня vs неделя)
    week_avg_score = sum(p.score or 0 for p in posts_week) / len(posts_week) if posts_week else 1
    today_avg_score = sum(p.score or 0 for p in posts_today) / len(posts_today) if posts_today else 0
    growth_rate = ((today_avg_score - week_avg_score) / week_avg_score * 100) if week_avg_score > 0 else 0
    
    # Вирусные посты (>1000 score)
    viral_posts = [
        {'title': p.title, 'score': p.score, 'comments': p.num_comments}
        for p in posts_today if p.score and p.score > 1000
    ]
    
    # Извлечение конкретных игр
    mentioned_games = extract_game_mentions(posts_today)
    
    # Механики и жанры
    mechanics_counter = Counter()
    themes_counter = Counter()
    
    keywords_mechanics = {
        'roguelike': ['roguelike', 'roguelite', 'rogue-like'],
        'deckbuilder': ['deckbuilder', 'deck builder', 'card game', 'tcg'],
        'metroidvania': ['metroidvania', 'metroid'],
        'survival': ['survival', 'survive'],
        'extraction': ['extraction', 'tarkov-like'],
        'automation': ['automation', 'factory', 'satisfactory-like'],
        'souls-like': ['souls-like', 'soulslike', 'dark souls'],
        'city-builder': ['city builder', 'city building', 'settlement'],
        'tower-defense': ['tower defense', 'td game']
    }
    
    keywords_themes = {
        'cozy': ['cozy', 'chill', 'relaxing', 'wholesome'],
        'horror': ['horror', 'scary', 'creepy', 'psychological'],
        'cyberpunk': ['cyberpunk', 'neon', 'dystopian'],
        'fantasy': ['fantasy', 'medieval', 'magic'],
        'sci-fi': ['sci-fi', 'space', 'futuristic'],
        'pixel-art': ['pixel art', '8-bit', '16-bit', 'retro']
    }
    
    for post in posts_today:
        text = (post.title + ' ' + (post.text or '')).lower()
        
        for mechanic, keywords in keywords_mechanics.items():
            if any(kw in text for kw in keywords):
                mechanics_counter[mechanic] += post.score or 1
        
        for theme, keywords in keywords_themes.items():
            if any(kw in text for kw in keywords):
                themes_counter[theme] += post.score or 1
    
    top_mechanics = [m for m, _ in mechanics_counter.most_common(5)]
    top_themes = [t for t, _ in themes_counter.most_common(5)]
    
    # Растущие механики (сравнение с прошлой неделей)
    week_mechanics = Counter()
    for post in posts_week:
        text = (post.title + ' ' + (post.text or '')).lower()
        for mechanic, keywords in keywords_mechanics.items():
            if any(kw in text for kw in keywords):
                week_mechanics[mechanic] += 1
    
    emerging_mechanics = []
    for mechanic in top_mechanics:
        today_count = mechanics_counter[mechanic]
        week_count = week_mechanics[mechanic] or 1
        growth = ((today_count - week_count) / week_count * 100)
        if growth > 50:  # >50% рост
            emerging_mechanics.append({'mechanic': mechanic, 'growth': round(growth, 1)})
    
    # Извлечь топ термины
    all_words = []
    for post in posts_today:
        words = re.findall(r'\b[a-zA-Z]{4,}\b', post.title.lower())
        all_words.extend(words)
    
    stop_words = {'game', 'indie', 'this', 'that', 'with', 'from', 'have', 'been', 'what', 'your', 'about', 'like'}
    word_counts = Counter(w for w in all_words if w not in stop_words)
    top_terms = [w for w, _ in word_counts.most_common(8)]
    
    # Определить sentiment
    positive_keywords = ['amazing', 'love', 'great', 'awesome', 'beautiful', 'recommend', 'masterpiece']
    negative_keywords = ['disappointed', 'boring', 'bad', 'waste', 'refund']
    
    positive_count = sum(1 for p in posts_today if any(kw in (p.title + ' ' + (p.text or '')).lower() for kw in positive_keywords))
    negative_count = sum(1 for p in posts_today if any(kw in (p.title + ' ' + (p.text or '')).lower() for kw in negative_keywords))
    
    if positive_count > negative_count * 2:
        sentiment = 'очень позитивный'
    elif positive_count > negative_count:
        sentiment = 'позитивный'
    else:
        sentiment = 'смешанный'
    
    # Инвестиционные сигналы
    investment_signals = []
    
    if growth_rate > 100:
        investment_signals.append('explosive_growth')
    if len(viral_posts) >= 3:
        investment_signals.append('high_virality')
    if total_comments > 1000:
        investment_signals.append('strong_engagement')
    if avg_ratio > 0.9:
        investment_signals.append('community_consensus')
    
    # Trending patterns
    trending_patterns = []
    if 'roguelike' in top_mechanics and 'deckbuilder' in top_mechanics:
        trending_patterns.append('roguelike_deckbuilder_fusion')
    if 'cozy' in top_themes:
        trending_patterns.append('cozy_gaming_wave')
    if growth_rate > 50:
        trending_patterns.append('momentum_building')
    
    return {
        'total_score': total_score,
        'total_comments': total_comments,
        'avg_upvote_ratio': round(avg_ratio, 2),
        'growth_rate': round(growth_rate, 1),
        'sentiment': sentiment,
        'top_mechanics': top_mechanics,
        'top_themes': top_themes,
        'top_terms': top_terms,
        'viral_posts': viral_posts[:5],
        'mentioned_games': mentioned_games[:10],
        'emerging_mechanics': emerging_mechanics,
        'trending_patterns': trending_patterns,
        'investment_signals': investment_signals
    }

def extract_game_mentions(posts):
    """Извлечь упоминания конкретных игр"""
    game_pattern = r'\b([A-Z][a-zA-Z\s]{2,30})\b'
    game_mentions = Counter()
    
    for post in posts:
        matches = re.findall(game_pattern, post.title)
        for match in matches:
            if len(match.split()) <= 4:  # Название игры обычно 1-4 слова
                game_mentions[match.strip()] += post.score or 1
    
    # Фильтр общих слов
    common_words = {'Indie', 'Game', 'Looking', 'Just', 'Need', 'What', 'Best', 'Games', 'Help'}
    return [game for game, _ in game_mentions.most_common(15) if game not in common_words]

def generate_detailed_recommendations(analysis):
    """Генерация детальных инвестиционных рекомендаций"""
    
    recs = []
    
    # 1. Горячие механики с конкретикой
    if analysis['top_mechanics']:
        top_3 = ', '.join(analysis['top_mechanics'][:3])
        recs.append(f"🎮 **Топ механики:** {top_3}. Community score: {analysis['total_score']}. "
                   f"Рекомендация: искать undermarketed игры в Steam/Itch с комбинацией этих механик.")
    
    # 2. Растущие механики (emerging trends)
    if analysis['emerging_mechanics']:
        for em in analysis['emerging_mechanics'][:2]:
            recs.append(f"📈 **Растущий тренд:** {em['mechanic']} показывает рост {em['growth']}% за неделю. "
                       f"СРОЧНО: Искать early-stage проекты в этом жанре для раннего инвестирования.")
    
    # 3. Вирусный потенциал
    if analysis['viral_posts']:
        top_viral = analysis['viral_posts'][0]
        recs.append(f"🔥 **Вирусный контент:** '{top_viral['title'][:50]}...' набрал {top_viral['score']} upvotes и {top_viral['comments']} комментов. "
                   f"Механики из этого поста имеют доказанный product-market fit.")
    
    # 4. Конкретные игры
    if analysis['mentioned_games']:
        games_str = ', '.join(analysis['mentioned_games'][:3])
        recs.append(f"💎 **Упоминаются игры:** {games_str}. "
                   f"Действие: найти аналоги на ранних стадиях + проанализировать их GAP scores.")
    
    # 5. Growth rate анализ
    if analysis['growth_rate'] > 100:
        recs.append(f"🚀 **КРИТИЧЕСКИЙ СИГНАЛ:** Активность выросла на {analysis['growth_rate']}% за неделю! "
                   f"Это explosive growth - СРОЧНО выделить бюджет на поиск игр в этих категориях.")
    elif analysis['growth_rate'] > 50:
        recs.append(f"📊 **Растущий интерес:** +{analysis['growth_rate']}% активности за неделю. "
                   f"Тренд набирает обороты - оптимальное окно для early investment.")
    
    # 6. Community engagement
    if analysis['total_comments'] > 1000:
        recs.append(f"💬 **Сильное вовлечение:** {analysis['total_comments']} комментариев = готовая активная аудитория. "
                   f"GTM стратегия: community-first подход через Reddit будет эффективен.")
    
    # 7. Sentiment анализ
    if analysis['sentiment'] == 'очень позитивный':
        recs.append(f"😊 **{analysis['sentiment'].upper()} sentiment** (upvote ratio {analysis['avg_upvote_ratio']}). "
                   f"Сообщество открыто к новым играм - высокий conversion rate для маркетинга.")
    
    # 8. Investment signals
    if 'explosive_growth' in analysis['investment_signals']:
        recs.append(f"⚠️ **ALERT:** Explosive growth обнаружен. Рекомендуем немедленный shortlist игр в этих жанрах.")
    
    if 'community_consensus' in analysis['investment_signals']:
        recs.append(f"✅ **Strong consensus:** High upvote ratio означает низкий риск негативных отзывов.")
    
    # 9. Итоговая стратегия
    action_items = []
    if analysis['emerging_mechanics']:
        action_items.append(f"искать {analysis['emerging_mechanics'][0]['mechanic']}")
    if analysis['mentioned_games']:
        action_items.append(f"анализировать аналоги {analysis['mentioned_games'][0]}")
    
    if action_items:
        recs.append(f"🎯 **Action Plan:** В течение 48 часов: {' + '.join(action_items)}. "
                   f"Expected ROI: высокий при раннем входе.")
    
    return recs


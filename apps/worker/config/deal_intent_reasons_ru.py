"""
Словарь перевода reasons на русский язык для Deals / Publisher Intent
Используется в API и UI для отображения понятных пояснений
"""

REASONS_RU_MAPPING = {
    # Intent reasons
    "no_publisher_on_steam": "Нет издателя на Steam",
    "self_published": "Самоиздание",
    "self_published_on_steam": "Самоиздание",
    "stage_bonus": "Бонус за стадию",
    "stage_coming_soon": "Скоро релиз (окно для издателя)",
    "stage_early_access": "Ранний доступ (потенциал роста)",
    "stage_demo": "Есть демо (лучше для сделки)",
    "stage_penalty_released": "Уже выпущено (хуже для издателя)",
    "contacts_available": "Есть контакты",
    "has_discord": "Есть Discord",
    "has_website": "Есть сайт",
    "no_contacts": "Нет контактов/Discord/сайта",
    "reviews_growth_30d": "Рост отзывов за 30 дней",
    "reviews_30d_10": "Активность: 10+ отзывов за 30 дней",
    "reviews_30d_20": "Активность: 20+ отзывов за 30 дней",
    "reviews_30d_50": "Активность: 50+ отзывов за 30 дней",
    "reviews_30d_100": "Активность: 100+ отзывов за 30 дней",
    "known_publisher_penalty": "Известный издатель (меньше потенциал)",
    "old_release_penalty": "Старый релиз (меньше потенциал)",
    "publisher_keywords_found": "Есть сигналы поиска издателя",
    "looking_for_publisher": "Ищет издателя",
    "funding": "Ищет финансирование",
    "pitch_deck": "Есть pitch deck",
    "marketing_help": "Нужна помощь с маркетингом",
    "self_published_early": "Самоиздание на ранней стадии",
    "has_publisher": "Есть издатель",
    "stage_early_access_fresh": "Свежий ранний доступ (<6 мес)",
    "stage_early_access_old": "Старый ранний доступ (>18 мес)",
    "stage_released_fresh": "Очень свежий релиз (<3 мес)",
    "stage_released": "Свежий релиз (<12 мес)",
    "stage_released_medium": "Средний релиз (1-2 года)",
    "stage_released_unknown": "Релиз (дата неизвестна)",
    "no_reviews_need_marketing": "Нет отзывов (нужен маркетинг)",
    "low_reviews_need_marketing": "Очень мало отзывов (нужен маркетинг)",
    "few_reviews": "Мало отзывов",
    "many_reviews_no_activity": "Много отзывов, но нет активности",
    "has_demo_early_stage": "Есть демо на ранней стадии",
    "free_game": "Бесплатная игра",
    "very_low_price": "Очень низкая цена (<5€)",
    "medium_price": "Средняя цена (10-20€)",
    "demo_no_traction": "Есть демо, но нет активности",
    "no_demo": "Нет демо",
    "no_contacts": "Нет контактов",
    "zero_reviews": "Нет отзывов",
    "very_few_reviews": "Очень мало отзывов (<10)",
    
    # Quality reasons
    "positive_ratio_95pct": "Очень высокий рейтинг (95%+)",
    "positive_ratio_90pct": "Очень высокий рейтинг (90%+)",
    "positive_ratio_85pct": "Хороший рейтинг (85%+)",
    "positive_ratio_80pct": "Хороший рейтинг (80%+)",
    "positive_ratio_75pct": "Приемлемый рейтинг (75%+)",
    "positive_ratio_70pct": "Средний рейтинг (70%+)",
    "positive_ratio_60pct": "Низкий рейтинг (60%+)",
    "high_quality_reviews": "Высокое качество отзывов",
    "quality_reviews_ok": "Приемлемое качество отзывов",
    "reviews_growth": "Рост отзывов",
    "has_demo": "Есть демо",
    "low_reviews_volume": "Мало отзывов (пока слабая база)",
    "no_reviews_30d": "Нет отзывов за 30 дней",
}

def translate_reason_to_ru(reason: str) -> str:
    """
    Переводит reason code на русский язык.
    Если маппинга нет, возвращает читаемую версию.
    """
    if reason in REASONS_RU_MAPPING:
        return REASONS_RU_MAPPING[reason]
    
    # Попытка извлечь информацию из формата "key_value" или "key_123"
    if "_" in reason:
        parts = reason.split("_")
        # Если последняя часть - число (например, "positive_ratio_97pct")
        if len(parts) > 1 and parts[-1].replace("pct", "").isdigit():
            key = "_".join(parts[:-1])
            value = parts[-1].replace("pct", "")
            if key == "positive_ratio":
                pct = int(value)
                if pct >= 95:
                    return f"Очень высокий рейтинг ({pct}%+)"
                elif pct >= 85:
                    return f"Хороший рейтинг ({pct}%+)"
                elif pct >= 75:
                    return f"Приемлемый рейтинг ({pct}%+)"
                else:
                    return f"Рейтинг {pct}%"
            elif key == "reviews_30d":
                return f"Активность: {value}+ отзывов за 30 дней"
    
    # Fallback: делаем читаемую версию
    return reason.replace("_", " ").title()

def translate_reasons_list(reasons: list) -> list:
    """Переводит список reasons на русский"""
    return [translate_reason_to_ru(r) for r in reasons]

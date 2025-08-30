def save_query_to_session(request, user_input, sql_query, result_data, visualization_suggestion):
    history = request.session.get('chat_history', [])
    history.append({
        'type': 'query',
        'user_input': user_input,
        'sql_query': sql_query,
        'result_summary': {
            'rows': len(result_data),
            'columns': list(result_data[0].keys()) if result_data else [],
        },
        'visualization_suggestion': visualization_suggestion,
    })
    request.session['chat_history'] = history
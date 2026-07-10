PAGE_SIZE_OPTIONS = (10, 20, 50)


def paginate_query(query, page=1, page_size=10):
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = 10

    page = max(page, 1)
    page_size = page_size if page_size in PAGE_SIZE_OPTIONS else 10
    total_count = query.count()
    total_pages = max((total_count + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    page_start = max(1, page - 2)
    page_end = min(total_pages, page + 2)

    return {
        "items": query.offset((page - 1) * page_size).limit(page_size).all(),
        "page": page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": max(page - 1, 1),
        "next_page": min(page + 1, total_pages),
        "page_numbers": list(range(page_start, page_end + 1)),
    }

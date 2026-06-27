import httpx


def download_image(url: str, *, timeout: float = 30.0) -> bytes:
    """Download the raw bytes of an image from a URL.

    WhatsApp (Green API) delivers images as a directly downloadable URL, so this
    is enough to fetch the photo referenced by ``imagen_ref``.
    """
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content

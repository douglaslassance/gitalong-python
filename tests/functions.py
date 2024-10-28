from PIL import Image


def save_image(filename: str, image_format: str = "JPEG"):
    """Saves a blank image to file.

    Args:
        filename (str): Where to save the image.
        image_format (str, optional): The image format to use. Defaults to "JPEG".
    """
    image = Image.new(mode="RGB", size=(256, 256))
    image.save(filename, image_format)

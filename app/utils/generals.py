import logging


def getProjectAvatarLetter(project_name: str) -> str:
    all_words = project_name.split()
    initials = "".join(word[0].upper() for word in all_words[:3])
    return initials


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pillar.scheduler")

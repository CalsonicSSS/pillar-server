def getProjectAvatarLetter(project_name: str) -> str:
    all_words = project_name.split()
    initials = "".join(word[0].upper() for word in all_words[:3])
    return initials

def register(email):
    if db.users.find(email):
        raise ValueError('taken')
    return db.users.insert(email)

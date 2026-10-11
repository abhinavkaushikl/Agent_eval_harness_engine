# expect: api_endpoint -- every function is a Flask route handler (@app.get/@app.post with a "/" path) and none touches SQL.
from flask import Flask, jsonify, request

app = Flask(__name__)

_TODOS: dict[int, str] = {}


@app.get("/todos/<int:todo_id>")
def get_todo(todo_id: int):
    if todo_id not in _TODOS:
        return jsonify(error="not found"), 404
    return jsonify(id=todo_id, title=_TODOS[todo_id])


@app.post("/todos")
def create_todo():
    title = request.get_json()["title"]
    todo_id = len(_TODOS) + 1
    _TODOS[todo_id] = title
    return jsonify(id=todo_id, title=title), 201

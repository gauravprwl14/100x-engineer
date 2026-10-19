import unittest

from todo.todo_list import TodoList


class TodoListTest(unittest.TestCase):
    def test_add_then_remove(self):
        todos = TodoList()
        todo = todos.add("buy milk")
        todos.remove(todo.todo_id)
        self.assertEqual(todos.open_todos(), [])

    def test_remove_unknown_id_raises(self):
        with self.assertRaises(KeyError):
            TodoList().remove(99)


if __name__ == "__main__":
    unittest.main()

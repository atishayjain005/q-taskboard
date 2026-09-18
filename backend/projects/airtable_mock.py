"""Test double for Airtable. Do not use in production export code."""


class MockAirtableClient:
    def __init__(self):
        self.records = {}
        self.create_calls = []
        self.update_calls = []
        self._create_outcomes = []
        self._update_outcomes = []
        self._next_id = 0

    def queue_create(self, *outcomes):
        self._create_outcomes.extend(outcomes)

    def queue_update(self, *outcomes):
        self._update_outcomes.extend(outcomes)

    def create(self, fields):
        self.create_calls.append(dict(fields))
        self._raise_if_queued(self._create_outcomes)
        self._next_id += 1
        record_id = f'recMOCK{self._next_id:010d}'
        self.records[record_id] = dict(fields)
        return {'id': record_id, 'fields': dict(fields)}

    def update(self, record_id, fields):
        self.update_calls.append((record_id, dict(fields)))
        self._raise_if_queued(self._update_outcomes)
        if record_id not in self.records:
            raise KeyError(f'unknown record {record_id}')
        self.records[record_id] = dict(fields)
        return {'id': record_id, 'fields': dict(fields)}

    def _raise_if_queued(self, queue):
        if not queue:
            return
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

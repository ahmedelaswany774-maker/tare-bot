from pathlib import Path

path = Path('.github/workflows/story-bot.yml')
text = path.read_text()
assert text.startswith('name: Story Bot - Series Publisher\n')
assert "    - cron: '0 3,9,15,21 * * *'" in text
assert '  workflow_dispatch:' in text
assert 'jobs:' in text
assert '  run-bot:' in text
assert 'if: ${{ inputs.publish_short == true }}' in text
assert text.count('steps:') == 1
print('workflow structure checks: OK')
print('schedule: OK')
print('workflow_dispatch: OK')
print('jobs: OK')
print('short condition: OK')

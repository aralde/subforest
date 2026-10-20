# Notes

## Create a note

`POST /v1/notes` with a JSON body containing `title` and `body`.

## Update a note

`PATCH /v1/notes/{id}` updates only the fields you send. Include `version` to avoid overwriting concurrent edits.

## Delete a note

`DELETE /v1/notes/{id}` moves the note to the trash for 30 days.

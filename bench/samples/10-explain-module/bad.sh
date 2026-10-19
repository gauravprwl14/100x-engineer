cat > "$BENCH_TEXT" <<'MD'
## Overview

The retry module is a module that handles retrying of HTTP requests in the http_client package, and it does this by wrapping a send function that you pass in, calling it in a loop, and checking the result each time to decide whether it should try again or not, which depends on a number of factors including the status code that came back and the kind of method that was used, as well as some headers that might have been present on the request or the response.

It is quite robust and handles most cases well.
MD

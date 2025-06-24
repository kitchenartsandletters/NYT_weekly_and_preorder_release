FROM postgres:alpine

# Set environment variable for Postgres password (host/user/db will be passed via CMD)
ENV PGPASSWORD=ABqDNeODAwEJHwcHsRrLADKffhoRKUVn

# Copy schema file from nested db directory inside refactor
COPY db/schema.sql /app/schema.sql

# Default CMD (can override if needed)
CMD ["psql", "-h", "postgres.railway.internal", "-U", "postgres", "-d", "railway", "-f", "/app/schema.sql"]
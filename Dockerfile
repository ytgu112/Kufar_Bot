FROM python:3.11-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --ingroup app --no-create-home app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY . .

# Create data and logs directories for volumes
RUN mkdir -p data logs && chown -R app:app /app

# Make entrypoint executable
RUN chmod +x entrypoint.sh

USER app

ENTRYPOINT ["/app/entrypoint.sh"]

# Run the bot
CMD ["python", "main.py"]

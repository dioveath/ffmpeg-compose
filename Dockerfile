FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu24.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies for ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    yasm \
    nasm \
    cmake \
    libtool \
    libc6 \
    libc6-dev \
    unzip \
    wget \
    libnuma-dev \
    pkg-config \
    git \
    # Dev libraries for https and subtitles
    gnutls-dev \
    libass-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libfribidi-dev \
    libharfbuzz-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Build nv-codec headers
RUN git clone https://git.videolan.org/git/ffmpeg/nv-codec-headers.git && \
    cd nv-codec-headers && \
    make install

# Build x265
RUN git clone https://github.com/videolan/x265.git && \
    cd x265/build/linux && \
    cmake -G "Unix Makefiles" -DCMAKE_INSTALL_PREFIX="/usr/local" ../../source && \
    make -j$(nproc) && \
    make install

RUN git clone https://git.ffmpeg.org/ffmpeg.git

WORKDIR /build/ffmpeg
RUN ./configure \
      --enable-gpl \
      --enable-libx265 \
      --enable-nonfree \
      --enable-cuda-nvcc \
      --enable-nvdec \
      --enable-nvenc \
      --enable-libnpp \
      --extra-cflags="-I/usr/local/cuda/include" \
      --extra-ldflags="-L/usr/local/cuda/lib64" \
      --enable-gnutls \
      --enable-libass \
      --enable-libfontconfig \
      --enable-libfreetype \
      --enable-libfribidi \
      --enable-libharfbuzz \
      --disable-static \
      --enable-shared && \
    make -j$(nproc) && \
    make install


# FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu24.04    
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive

# Install Python and other runtime dependencies
RUN apt-get update && \
    apt-get install -y python3.12 python3-pip python3.12-venv fontconfig libass9 libgnutls30 libfreetype6 libfribidi0 libharfbuzz0b libnuma1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/ /usr/local/
RUN ldconfig # update the library cache so system can find new ffmpeg shared libraries

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN mkdir -p /usr/local/share/fonts    
COPY /fonts /usr/local/share/fonts
RUN fc-cache -f -v

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose ports
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
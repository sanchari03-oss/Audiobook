/**
 * AudioEngine - High-Performance Architectural & Data Engine for Audiobooks
 * Inspired by Martin Kleppmann's "Designing Data-Intensive Applications" (DDIA).
 *
 * Subsystems:
 * 1. ManifestManager (DDIA Ch 3 & 4): Partitioned manifests & on-demand lazy loading.
 * 2. RangeSliceDownloader (DDIA Ch 8): Resumable 2MB byte-range slicing for unreliable networks.
 * 3. PlaybackJournal (DDIA Ch 10 & 11): Event-sourced append-only playback journal & state folding.
 * 4. InvertedSearchIndex (DDIA Ch 3): In-memory inverted search index for sub-millisecond offline lookup.
 */

(function(root) {
  'use strict';

  // =========================================================================
  // 1. MANIFEST MANAGER (DDIA Ch 3 & 4: Partitioned Manifests & Decoupling)
  // =========================================================================
  class ManifestManager {
    constructor(db = null) {
      this.db = db;
      this.memoryCache = new Map(); // bookId -> manifestData
      this.inFlightRequests = new Map(); // bookId -> Promise<manifestData>
      this.engine = null;
    }

    setDb(db) {
      this.db = db;
    }

    setEngine(engine) {
      this.engine = engine;
    }

    /**
     * Ensure a book has its chapters loaded. If already present, returns instantly.
     * Otherwise fetches <book_dir>/manifest.json on-demand and caches in memory & IndexedDB.
     */
    async ensureManifest(book) {
      if (!book) return null;

      // 1. Fast path: chapters already populated in memory
      if (Array.isArray(book.chapters) && book.chapters.length > 0) {
        if (!this.memoryCache.has(book.id)) {
          this.memoryCache.set(book.id, {
            id: book.id,
            chapters: book.chapters,
            total_tracks: book.total_tracks || book.chapters.length,
            total_duration: book.total_duration
          });
        }
        return book;
      }

      // 2. Check memory cache
      if (this.memoryCache.has(book.id)) {
        const cached = this.memoryCache.get(book.id);
        book.chapters = cached.chapters;
        book.total_tracks = cached.total_tracks || cached.chapters.length;
        if (cached.total_duration) book.total_duration = cached.total_duration;
        return book;
      }

      // 3. De-duplicate concurrent requests for the same book manifest
      if (this.inFlightRequests.has(book.id)) {
        const manifest = await this.inFlightRequests.get(book.id);
        book.chapters = manifest.chapters;
        return book;
      }

      // 4. Check IndexedDB cached book object
      if (this.db) {
        try {
          const dbBook = await this._getFromDB("books", book.id);
          if (dbBook && Array.isArray(dbBook.chapters) && dbBook.chapters.length > 0) {
            book.chapters = dbBook.chapters;
            book.total_tracks = dbBook.total_tracks || dbBook.chapters.length;
            if (dbBook.total_duration) book.total_duration = dbBook.total_duration;
            this.memoryCache.set(book.id, dbBook);
            if (this.engine && this.engine.searchIndex) {
              this.engine.searchIndex.updateBookChapters(book.id, book.chapters);
            }
            return book;
          }
        } catch (e) {
          // IndexedDB read failed, fallback to network fetch
        }
      }

      // 5. Network fetch: partitioned <book_folder>/manifest.json
      const fetchPromise = (async () => {
        try {
          let manifestUrl = book.manifest_url;
          if (!manifestUrl) {
            if (book.cover_url) {
              const lastSlash = book.cover_url.lastIndexOf('/');
              manifestUrl = lastSlash !== -1
                ? `${book.cover_url.substring(0, lastSlash)}/manifest.json`
                : `${encodeURIComponent(book.title)}/manifest.json`;
            } else {
              manifestUrl = `${encodeURIComponent(book.title)}/manifest.json`;
            }
          }

          // Append timestamp to avoid stale HTTP cache on initial load
          const fetchUrl = manifestUrl.includes('?') ? `${manifestUrl}&_t=${Date.now()}` : `${manifestUrl}?_t=${Date.now()}`;
          const res = await fetch(fetchUrl);
          if (!res.ok) {
            // Retry without cache buster
            const retryRes = await fetch(manifestUrl);
            if (!retryRes.ok) throw new Error(`HTTP ${retryRes.status} loading manifest`);
            return await retryRes.json();
          }
          return await res.json();
        } finally {
          this.inFlightRequests.delete(book.id);
        }
      })();

      this.inFlightRequests.set(book.id, fetchPromise);

      try {
        const manifest = await fetchPromise;
        if (manifest && Array.isArray(manifest.chapters)) {
          book.chapters = manifest.chapters;
          book.total_tracks = manifest.total_tracks || manifest.chapters.length;
          if (manifest.total_duration) book.total_duration = manifest.total_duration;
          book.has_manifest = true;

          // Cache in memory
          this.memoryCache.set(book.id, manifest);

          // Persist enriched book in IndexedDB for 100% offline subsequent opens
          if (this.db) {
            try {
              await this._putToDB("books", book);
            } catch (err) {
              // Non-fatal IndexedDB write
            }
          }

          // Feed chapter tokens into in-memory search index
          if (this.engine && this.engine.searchIndex) {
            this.engine.searchIndex.updateBookChapters(book.id, book.chapters);
          }
        }
      } catch (err) {
        console.warn(`ManifestManager: could not load manifest for "${book.title}":`, err);
      }

      return book;
    }

    /**
     * Asynchronously prefetch manifests for nearby books in the background.
     */
    prefetchNearby(booksList, activeIdx = 0, count = 3) {
      if (!Array.isArray(booksList) || booksList.length === 0) return;
      const candidates = [];
      for (let i = 1; i <= count; i++) {
        const next = booksList[activeIdx + i];
        if (next && (!next.chapters || next.chapters.length === 0)) candidates.push(next);
        const prev = booksList[activeIdx - i];
        if (prev && (!prev.chapters || prev.chapters.length === 0)) candidates.push(prev);
      }
      candidates.forEach(b => {
        if ('requestIdleCallback' in window) {
          window.requestIdleCallback(() => this.ensureManifest(b));
        } else {
          setTimeout(() => this.ensureManifest(b), 250);
        }
      });
    }

    _getFromDB(storeName, key) {
      return new Promise((resolve, reject) => {
        if (!this.db) return resolve(null);
        try {
          const tx = this.db.transaction(storeName, "readonly");
          const req = tx.objectStore(storeName).get(key);
          req.onsuccess = () => resolve(req.result || null);
          req.onerror = () => reject(req.error);
        } catch (e) {
          resolve(null);
        }
      });
    }

    _putToDB(storeName, value) {
      return new Promise((resolve, reject) => {
        if (!this.db) return resolve();
        try {
          const tx = this.db.transaction(storeName, "readwrite");
          const req = tx.objectStore(storeName).put(value);
          req.onsuccess = () => resolve();
          req.onerror = () => reject(req.error);
        } catch (e) {
          resolve();
        }
      });
    }
  }


  // =========================================================================
  // 2. RESUMABLE 2MB BYTE-RANGE SLICING (DDIA Ch 8 - Unreliable Networks)
  // =========================================================================
  class RangeSliceDownloader {
    constructor(db = null) {
      this.db = db;
      this.SLICE_SIZE = 2 * 1024 * 1024; // 2MB chunking
      this.activeDownloads = new Map(); // blobKey -> AbortController
    }

    setDb(db) {
      this.db = db;
    }

    /**
     * Inspect IndexedDB audio_slices store for previously downloaded slices for this track.
     * Returns an array of existing slices sorted by sliceIndex.
     */
    async getStoredSlices(blobKey) {
      if (!this.db) return [];
      return new Promise((resolve) => {
        try {
          const tx = this.db.transaction("audio_slices", "readonly");
          const store = tx.objectStore("audio_slices");
          let req;
          if (store.indexNames.contains("blobKey")) {
            req = store.index("blobKey").getAll(blobKey);
          } else {
            req = store.getAll();
          }

          req.onsuccess = () => {
            const results = (req.result || []).filter(item => item.blobKey === blobKey);
            results.sort((a, b) => a.sliceIndex - b.sliceIndex);
            resolve(results);
          };
          req.onerror = () => resolve([]);
        } catch (e) {
          resolve([]);
        }
      });
    }

    /**
     * Save an individual 2MB slice into IndexedDB audio_slices store.
     */
    async saveSlice(sliceRecord) {
      if (!this.db) return;
      return new Promise((resolve, reject) => {
        try {
          const tx = this.db.transaction("audio_slices", "readwrite");
          const store = tx.objectStore("audio_slices");
          const req = store.put(sliceRecord);
          req.onsuccess = () => resolve();
          req.onerror = () => reject(req.error);
        } catch (e) {
          reject(e);
        }
      });
    }

    /**
     * Assemble all slices for a track in exact sequential order into a single unified Blob.
     */
    async assembleBlob(blobKey, mimeType = "audio/mpeg") {
      const slices = await this.getStoredSlices(blobKey);
      if (!slices || slices.length === 0) return null;

      slices.sort((a, b) => a.sliceIndex - b.sliceIndex);
      const buffers = slices.map(s => s.data);
      const unifiedBlob = new Blob(buffers, { type: mimeType });

      // Persist the assembled unified Blob into audioblobs store
      if (this.db) {
        try {
          const tx = this.db.transaction("audioblobs", "readwrite");
          tx.objectStore("audioblobs").put(unifiedBlob, blobKey);
        } catch (e) {
          // Non-fatal if already present
        }
      }

      return unifiedBlob;
    }

    /**
     * Download track in 2MB slices with Range headers.
     * Resumes from the exact next missing slice if interrupted. Zero restarts from 0%!
     */
    async downloadTrack(url, blobKey, options = {}) {
      const { signal, onProgress, fileSize } = options;

      // 1. Check if unified blob already exists in audioblobs store
      if (this.db) {
        const existingBlob = await new Promise(resolve => {
          try {
            const tx = this.db.transaction("audioblobs", "readonly");
            const req = tx.objectStore("audioblobs").get(blobKey);
            req.onsuccess = () => resolve(req.result || null);
            req.onerror = () => resolve(null);
          } catch (e) {
            resolve(null);
          }
        });
        if (existingBlob && existingBlob.size > 1000) {
          if (onProgress) onProgress({ downloadedBytes: existingBlob.size, totalBytes: existingBlob.size, percent: 100 });
          return existingBlob;
        }
      }

      // 2. Determine total file size (from argument, HEAD request, or 0-byte probe)
      let totalBytes = fileSize || 0;
      let supportsRange = true;

      if (!totalBytes || totalBytes <= 0) {
        try {
          const headRes = await fetch(url, { method: "HEAD", signal });
          if (headRes.ok) {
            const cl = headRes.headers.get("content-length");
            if (cl) totalBytes = parseInt(cl, 10);
            const acceptRanges = headRes.headers.get("accept-ranges");
            if (acceptRanges === "none") supportsRange = false;
          }
        } catch (e) {
          // Fall through to probe range
        }
      }

      // If HEAD didn't yield totalBytes, probe with a 1-byte range request
      if (!totalBytes || totalBytes <= 0) {
        try {
          const probeRes = await fetch(url, { headers: { "Range": "bytes=0-0" }, signal });
          if (probeRes.status === 206) {
            const cr = probeRes.headers.get("content-range");
            if (cr) {
              const match = cr.match(/\/(\d+)/);
              if (match) totalBytes = parseInt(match[1], 10);
            }
          } else if (probeRes.status === 200) {
            // Server ignored Range header and sent full payload
            supportsRange = false;
            const fullBlob = await probeRes.blob();
            if (this.db) {
              const tx = this.db.transaction("audioblobs", "readwrite");
              tx.objectStore("audioblobs").put(fullBlob, blobKey);
            }
            return fullBlob;
          }
        } catch (e) {
          // Probe error
        }
      }

      // Fallback: If server does not support byte ranges, fetch stream and slice in memory
      if (!supportsRange || !totalBytes || totalBytes <= 0) {
        const fullRes = await fetch(url, { signal });
        if (!fullRes.ok) throw new Error(`HTTP ${fullRes.status} fetching audio`);
        const fullBlob = await fullRes.blob();
        if (this.db) {
          const tx = this.db.transaction("audioblobs", "readwrite");
          tx.objectStore("audioblobs").put(fullBlob, blobKey);
        }
        return fullBlob;
      }

      // 3. Inspect existing slices for resumability (Zero restarts from 0%)
      const totalSlices = Math.ceil(totalBytes / this.SLICE_SIZE);
      const existingSlices = await this.getStoredSlices(blobKey);
      const downloadedIndices = new Set(existingSlices.map(s => s.sliceIndex));

      // Check if all slices already present
      if (downloadedIndices.size === totalSlices) {
        return await this.assembleBlob(blobKey);
      }

      let downloadedBytes = existingSlices.reduce((sum, s) => sum + (s.size || 0), 0);

      // 4. Download missing slices sequentially
      for (let sliceIdx = 0; sliceIdx < totalSlices; sliceIdx++) {
        if (signal && signal.aborted) {
          throw new DOMException("Download aborted", "AbortError");
        }

        // Skip already downloaded slices (RESUME CAPABILITY)
        if (downloadedIndices.has(sliceIdx)) {
          continue;
        }

        const startByte = sliceIdx * this.SLICE_SIZE;
        const endByte = Math.min((sliceIdx + 1) * this.SLICE_SIZE - 1, totalBytes - 1);

        let sliceSuccess = false;
        let lastError = null;

        for (let attempt = 1; attempt <= 4; attempt++) {
          if (signal && signal.aborted) throw new DOMException("Download aborted", "AbortError");

          try {
            const sliceRes = await fetch(url, {
              headers: { "Range": `bytes=${startByte}-${endByte}` },
              signal
            });

            if (sliceRes.status === 206) {
              const buffer = await sliceRes.arrayBuffer();
              const sliceRecord = {
                key: `${blobKey}_slice_${sliceIdx}`,
                blobKey: blobKey,
                sliceIndex: sliceIdx,
                totalSlices: totalSlices,
                startByte: startByte,
                endByte: endByte,
                totalBytes: totalBytes,
                size: buffer.byteLength,
                data: buffer,
                timestamp: Date.now()
              };

              await this.saveSlice(sliceRecord);
              downloadedIndices.add(sliceIdx);
              downloadedBytes += buffer.byteLength;
              sliceSuccess = true;

              if (onProgress) {
                const pct = Math.min(100, Math.round((downloadedBytes / totalBytes) * 100));
                onProgress({ downloadedBytes, totalBytes, percent: pct, sliceIndex: sliceIdx, totalSlices });
              }
              break;
            } else if (sliceRes.status === 200) {
              // Server doesn't support Range; fallback to full download
              const fullBuffer = await sliceRes.arrayBuffer();
              const fullBlob = new Blob([fullBuffer], { type: "audio/mpeg" });
              if (this.db) {
                const tx = this.db.transaction("audioblobs", "readwrite");
                tx.objectStore("audioblobs").put(fullBlob, blobKey);
              }
              return fullBlob;
            } else {
              throw new Error(`HTTP ${sliceRes.status}`);
            }
          } catch (err) {
            lastError = err;
            if (signal && signal.aborted) throw err;
            if (attempt < 4) {
              await new Promise(r => setTimeout(r, attempt * 800));
            }
          }
        }

        if (!sliceSuccess) {
          throw lastError || new Error(`Failed to download slice ${sliceIdx}`);
        }
      }

      // 5. Assemble unified blob from complete slices
      return await this.assembleBlob(blobKey);
    }

    /**
     * Delete all slices for a specific track or whole book from audio_slices store.
     */
    async clearSlices(blobKey) {
      if (!this.db) return;
      return new Promise((resolve) => {
        try {
          const tx = this.db.transaction("audio_slices", "readwrite");
          const store = tx.objectStore("audio_slices");
          const req = store.openCursor();
          req.onsuccess = (e) => {
            const cursor = e.target.result;
            if (cursor) {
              if (cursor.value.blobKey === blobKey || cursor.value.blobKey.startsWith(`${blobKey}_`)) {
                cursor.delete();
              }
              cursor.continue();
            } else {
              resolve();
            }
          };
          req.onerror = () => resolve();
        } catch (e) {
          resolve();
        }
      });
    }
  }


  // =========================================================================
  // 3. EVENT-SOURCED PLAYBACK JOURNAL (DDIA Ch 10 & 11)
  // =========================================================================
  class PlaybackJournal {
    constructor(db = null) {
      this.db = db;
      this.listeners = new Set();
    }

    setDb(db) {
      this.db = db;
    }

    addListener(callback) {
      this.listeners.add(callback);
      return () => this.listeners.delete(callback);
    }

    /**
     * Append an immutable playback event to the playback_events log.
     * Event schema: { timestamp, bookId, chapIdx, time, speed, eventType: 'play'|'pause'|'seek'|'finish' }
     */
    async recordEvent(eventData) {
      if (!eventData || !eventData.bookId) return;

      const event = {
        timestamp: Date.now(),
        bookId: String(eventData.bookId),
        chapIdx: Math.max(0, parseInt(eventData.chapIdx, 10) || 0),
        time: Math.round((Math.max(0, parseFloat(eventData.time) || 0)) * 100) / 100,
        speed: parseFloat(eventData.speed) || 1.0,
        eventType: eventData.eventType || "play" // 'play' | 'pause' | 'seek' | 'finish'
      };

      if (this.db) {
        try {
          const tx = this.db.transaction("playback_events", "readwrite");
          const store = tx.objectStore("playback_events");
          store.add(event);
        } catch (err) {
          console.warn("PlaybackJournal write failed:", err);
        }
      }

      // Notify reactive listeners
      this.listeners.forEach(fn => {
        try { fn(event); } catch (e) {}
      });

      return event;
    }

    /**
     * Retrieve all chronological playback events for a given bookId.
     */
    async getEvents(bookId) {
      if (!this.db) return [];
      return new Promise((resolve) => {
        try {
          const tx = this.db.transaction("playback_events", "readonly");
          const store = tx.objectStore("playback_events");
          let req;
          if (store.indexNames.contains("bookId")) {
            req = store.index("bookId").getAll(String(bookId));
          } else {
            req = store.getAll();
          }

          req.onsuccess = () => {
            const events = (req.result || []).filter(e => e.bookId === String(bookId));
            events.sort((a, b) => (a.timestamp - b.timestamp) || (a.id - b.id));
            resolve(events);
          };
          req.onerror = () => resolve([]);
        } catch (e) {
          resolve([]);
        }
      });
    }

    /**
     * Deterministically fold / reduce the event stream to restore the exact last position
     * without mutable state race conditions (DDIA Ch 10 & 11).
     */
    async reducePlaybackState(bookId, optionalEvents = null) {
      const events = optionalEvents || (await this.getEvents(bookId));

      const initialState = {
        bookId: String(bookId),
        chapIdx: 0,
        time: 0,
        speed: 1.0,
        status: "stopped", // 'stopped' | 'playing' | 'paused' | 'finished'
        lastPlayedTimestamp: 0,
        finishedChapters: new Set(),
        isBookFinished: false,
        totalEvents: 0
      };

      const reduced = events.reduce((state, evt) => {
        state.totalEvents++;
        state.lastPlayedTimestamp = evt.timestamp;

        if (typeof evt.speed === "number" && evt.speed > 0) {
          state.speed = evt.speed;
        }

        switch (evt.eventType) {
          case "play":
            state.status = "playing";
            state.chapIdx = evt.chapIdx;
            state.time = evt.time;
            break;

          case "pause":
            state.status = "paused";
            state.chapIdx = evt.chapIdx;
            state.time = evt.time;
            break;

          case "seek":
            state.chapIdx = evt.chapIdx;
            state.time = evt.time;
            break;

          case "finish":
            state.finishedChapters.add(evt.chapIdx);
            state.status = "finished";
            state.time = evt.time;
            break;
        }

        return state;
      }, initialState);

      return {
        bookId: reduced.bookId,
        chapIdx: reduced.chapIdx,
        time: reduced.time,
        speed: reduced.speed,
        status: reduced.status,
        lastPlayedTimestamp: reduced.lastPlayedTimestamp,
        finishedChapters: Array.from(reduced.finishedChapters),
        eventsCount: reduced.totalEvents
      };
    }

    /**
     * Clear all journal events for a given bookId.
     */
    async clearEvents(bookId) {
      if (!this.db) return;
      return new Promise((resolve) => {
        try {
          const tx = this.db.transaction("playback_events", "readwrite");
          const store = tx.objectStore("playback_events");
          const req = store.openCursor();
          req.onsuccess = (e) => {
            const cursor = e.target.result;
            if (cursor) {
              if (cursor.value.bookId === String(bookId)) cursor.delete();
              cursor.continue();
            } else {
              resolve();
            }
          };
          req.onerror = () => resolve();
        } catch (e) {
          resolve();
        }
      });
    }
  }


  // =========================================================================
  // 4. IN-MEMORY INVERTED SEARCH INDEX (DDIA Ch 3 - Fast Offline Search)
  // =========================================================================
  class InvertedSearchIndex {
    constructor() {
      // Map<token, Set<bookId>>
      this.tokenIndex = new Map();
      // Map<bookId, { book, fieldTokens }>
      this.documents = new Map();
      // Map<token, Map<bookId, score>>
      this.tokenScores = new Map();

      this.FIELD_WEIGHTS = {
        title: 5.0,
        author: 3.5,
        category: 3.0,
        chapter: 2.0,
        description: 1.0
      };
    }

    /**
     * Fast tokenizer: lowercases, removes non-alphanumeric noise, splits by whitespace.
     */
    tokenize(text) {
      if (!text || typeof text !== "string") return [];
      return text
        .toLowerCase()
        .replace(/['’]/g, "")
        .replace(/[^a-z0-9_\-\s]/g, " ")
        .split(/\s+/)
        .map(t => t.trim())
        .filter(t => t.length >= 2);
    }

    /**
     * Index a single book into the inverted index.
     */
    addBook(book) {
      if (!book || !book.id) return;
      this.removeBook(book.id);

      const bookId = String(book.id);
      this.documents.set(bookId, book);

      const indexField = (fieldTokens, weight) => {
        const counts = new Map();
        for (const token of fieldTokens) {
          counts.set(token, (counts.get(token) || 0) + 1);
        }

        counts.forEach((count, token) => {
          // Add to token -> Set<bookId>
          if (!this.tokenIndex.has(token)) {
            this.tokenIndex.set(token, new Set());
          }
          this.tokenIndex.get(token).add(bookId);

          // Add weighted TF score
          if (!this.tokenScores.has(token)) {
            this.tokenScores.set(token, new Map());
          }
          const scoreMap = this.tokenScores.get(token);
          const currentScore = scoreMap.get(bookId) || 0;
          scoreMap.set(bookId, currentScore + (count * weight));
        });
      };

      // 1. Index Title
      indexField(this.tokenize(book.title), this.FIELD_WEIGHTS.title);

      // 2. Index Author
      indexField(this.tokenize(book.author), this.FIELD_WEIGHTS.author);

      // 3. Index Category / Description
      if (book.category) indexField(this.tokenize(book.category), this.FIELD_WEIGHTS.category);
      if (book.description) indexField(this.tokenize(book.description), this.FIELD_WEIGHTS.description);

      // 4. Index Chapters (if loaded)
      if (Array.isArray(book.chapters)) {
        for (const chap of book.chapters) {
          if (chap && chap.name) {
            indexField(this.tokenize(chap.name), this.FIELD_WEIGHTS.chapter);
          }
        }
      }
    }

    /**
     * Incrementally update or index chapter titles when manifest is lazy loaded.
     */
    updateBookChapters(bookId, chapters) {
      const book = this.documents.get(String(bookId));
      if (!book || !Array.isArray(chapters)) return;
      book.chapters = chapters;
      this.addBook(book);
    }

    /**
     * Remove a book from all inverted index postings.
     */
    removeBook(bookId) {
      const id = String(bookId);
      this.documents.delete(id);
      this.tokenIndex.forEach((set) => set.delete(id));
      this.tokenScores.forEach((map) => map.delete(id));
    }

    /**
     * Build the entire inverted index from an array of books.
     */
    buildIndex(booksList) {
      this.tokenIndex.clear();
      this.documents.clear();
      this.tokenScores.clear();

      if (!Array.isArray(booksList)) return;
      for (const b of booksList) {
        this.addBook(b);
      }
    }

    /**
     * Sub-millisecond multi-word & prefix search queries across the library offline.
     * Evaluates multi-token queries with conjunctive (AND) intersection and ranked relevance.
     */
    search(query, options = {}) {
      const { limit = 50, prefix = true } = options;
      const qTokens = this.tokenize(query);
      if (qTokens.length === 0) {
        return Array.from(this.documents.values()).slice(0, limit);
      }

      // Collect candidate books for each query token
      const tokenCandidateSets = [];

      for (const qToken of qTokens) {
        const matchesForToken = new Map(); // bookId -> score

        // Exact match
        if (this.tokenIndex.has(qToken)) {
          const exactSet = this.tokenIndex.get(qToken);
          const scoreMap = this.tokenScores.get(qToken);
          exactSet.forEach(bId => {
            const score = scoreMap ? (scoreMap.get(bId) || 1.0) : 1.0;
            matchesForToken.set(bId, (matchesForToken.get(bId) || 0) + score * 1.5);
          });
        }

        // Prefix match (DDIA Ch 3)
        if (prefix && qToken.length >= 2) {
          for (const [indexedToken, bookSet] of this.tokenIndex.entries()) {
            if (indexedToken !== qToken && indexedToken.startsWith(qToken)) {
              const prefixScoreMap = this.tokenScores.get(indexedToken);
              bookSet.forEach(bId => {
                const score = prefixScoreMap ? (prefixScoreMap.get(bId) || 1.0) : 1.0;
                // Prefix match score penalty
                matchesForToken.set(bId, (matchesForToken.get(bId) || 0) + score * 0.85);
              });
            }
          }
        }

        tokenCandidateSets.push(matchesForToken);
      }

      if (tokenCandidateSets.length === 0) return [];

      // Conjunctive intersection: books that match ALL query tokens (AND logic)
      let combinedScores = new Map();
      const firstSet = tokenCandidateSets[0];

      firstSet.forEach((score, bId) => {
        let matchesAll = true;
        let totalScore = score;

        for (let i = 1; i < tokenCandidateSets.length; i++) {
          const subsequentSet = tokenCandidateSets[i];
          if (!subsequentSet.has(bId)) {
            matchesAll = false;
            break;
          }
          totalScore += subsequentSet.get(bId);
        }

        if (matchesAll) {
          combinedScores.set(bId, totalScore);
        }
      });

      // If conjunctive match returned 0 results, fall back to disjunctive (OR) ranking
      if (combinedScores.size === 0) {
        tokenCandidateSets.forEach(set => {
          set.forEach((score, bId) => {
            combinedScores.set(bId, (combinedScores.get(bId) || 0) + score);
          });
        });
      }

      // Sort matching books by descending relevance score
      const sortedBookIds = Array.from(combinedScores.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, limit)
        .map(entry => entry[0]);

      return sortedBookIds
        .map(id => this.documents.get(id))
        .filter(Boolean);
    }

    getStats() {
      return {
        indexedBooks: this.documents.size,
        distinctTokens: this.tokenIndex.size,
        totalPostings: Array.from(this.tokenIndex.values()).reduce((sum, set) => sum + set.size, 0)
      };
    }
  }


  // =========================================================================
  // 5. UNIFIED AUDIO ENGINE FACADE
  // =========================================================================
  class AudioEngine {
    constructor() {
      this.db = null;
      this.manifestManager = new ManifestManager();
      this.rangeSliceDownloader = new RangeSliceDownloader();
      this.playbackJournal = new PlaybackJournal();
      this.searchIndex = new InvertedSearchIndex();

      this.manifestManager.setEngine(this);
    }

    /**
     * Connect the AudioEngine to the open IndexedDB instance.
     */
    init(db) {
      this.db = db;
      this.manifestManager.setDb(db);
      this.rangeSliceDownloader.setDb(db);
      this.playbackJournal.setDb(db);
      return this;
    }
  }

  // Singleton instance
  const engine = new AudioEngine();

  // Export for Browser and Node.js
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      ManifestManager,
      RangeSliceDownloader,
      PlaybackJournal,
      InvertedSearchIndex,
      AudioEngine,
      engine
    };
  }

  if (typeof root !== 'undefined') {
    root.AudioEngine = engine;
    root.ManifestManager = ManifestManager;
    root.RangeSliceDownloader = RangeSliceDownloader;
    root.PlaybackJournal = PlaybackJournal;
    root.InvertedSearchIndex = InvertedSearchIndex;
  }
})(typeof self !== 'undefined' ? self : this);

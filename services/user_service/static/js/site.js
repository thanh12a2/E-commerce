(function () {
  const safeJsonParse = (rawValue, fallbackValue) => {
    try {
      return JSON.parse(rawValue);
    } catch (error) {
      return fallbackValue;
    }
  };

  const getCsrfToken = () => {
    const cookie = document.cookie || "";
    const parts = cookie.split(";").map((item) => item.trim());
    const tokenPair = parts.find((item) => item.startsWith("csrftoken="));
    return tokenPair ? decodeURIComponent(tokenPair.split("=")[1] || "") : "";
  };

  const loadConversationHistory = (storageKey) => {
    if (!storageKey || !window.localStorage) {
      return [];
    }

    const rawValue = window.localStorage.getItem(storageKey);
    if (!rawValue) {
      return [];
    }

    const parsed = safeJsonParse(rawValue, []);
    return Array.isArray(parsed) ? parsed : [];
  };

  const saveConversationHistory = (storageKey, historyItems) => {
    if (!storageKey || !window.localStorage) {
      return;
    }

    try {
      window.localStorage.setItem(storageKey, JSON.stringify(historyItems));
    } catch (error) {
      // Ignore quota/storage errors and keep chat usable.
    }
  };

  const clearConversationHistory = (storageKey) => {
    if (!storageKey || !window.localStorage) {
      return;
    }

    try {
      window.localStorage.removeItem(storageKey);
    } catch (error) {
      // Ignore storage cleanup errors to keep chat usable.
    }
  };

  const appendMessage = (log, role, text) => {
    const article = document.createElement("article");
    article.className = `assist-msg assist-msg-${role}`;
    const bubble = document.createElement("div");
    bubble.className = "assist-msg-bubble";

    if (role === "assistant") {
      const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
      let list = null;

      lines.forEach((rawLine) => {
        const line = rawLine.trim();
        if (!line) {
          list = null;
          return;
        }

        if (/^[-*]\s+/.test(line)) {
          if (!list) {
            list = document.createElement("ul");
            bubble.appendChild(list);
          }
          const item = document.createElement("li");
          item.textContent = line.replace(/^[-*]\s+/, "");
          list.appendChild(item);
          return;
        }

        list = null;
        const paragraph = document.createElement("p");
        paragraph.textContent = line;
        bubble.appendChild(paragraph);
      });

      if (!bubble.childNodes.length) {
        const paragraph = document.createElement("p");
        paragraph.textContent = "No response generated.";
        bubble.appendChild(paragraph);
      }
    } else {
      const paragraph = document.createElement("p");
      paragraph.textContent = text;
      bubble.appendChild(paragraph);
    }

    article.appendChild(bubble);
    log.appendChild(article);
    log.scrollTop = log.scrollHeight;
    return article;
  };

  const appendRecommendations = (log, recommendations) => {
    if (!Array.isArray(recommendations) || !recommendations.length) {
      return;
    }

    const container = document.createElement("div");
    container.className = "assist-recommend-grid";

    recommendations.slice(0, 5).forEach((item) => {
      const card = document.createElement("a");
      card.className = "assist-recommend-card";
      card.href = item.url || "#";

      const title = document.createElement("strong");
      title.textContent = item.name || "Product";

      const meta = document.createElement("span");
      const brand = item.brand || "N/A";
      const categoryName = item.category_name || item.category_slug || item.service || "Category";
      meta.textContent = `${categoryName} | ${brand}`;

      const price = document.createElement("span");
      price.textContent = `$${item.price || "0"} | Stock: ${item.stock || 0}`;

      card.appendChild(title);
      card.appendChild(meta);
      card.appendChild(price);
      container.appendChild(card);
    });

    log.appendChild(container);
    log.scrollTop = log.scrollHeight;
  };

  const appendCitations = (log, citations) => {
    if (!Array.isArray(citations) || !citations.length) {
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.className = "assist-citation-wrap";

    const title = document.createElement("p");
    title.className = "assist-citation-title";
    title.textContent = "Sources";
    wrapper.appendChild(title);

    const list = document.createElement("ul");
    list.className = "assist-citation-list";

    citations.slice(0, 3).forEach((item) => {
      const li = document.createElement("li");
      const anchor = document.createElement("a");
      anchor.href = item.url || "#";
      anchor.textContent = `${item.label}: ${item.detail}`;
      li.appendChild(anchor);
      list.appendChild(li);
    });

    wrapper.appendChild(list);
    log.appendChild(wrapper);
    log.scrollTop = log.scrollHeight;
  };

  const initChatbotWidgets = () => {
    const widgets = Array.from(document.querySelectorAll("[data-assist-panel]"));
    if (!widgets.length) {
      return;
    }

    const csrfToken = getCsrfToken();

    widgets.forEach((widget) => {
      const shell = widget.closest("[data-assist-shell]");
      const toggleButton = shell ? shell.querySelector("[data-assist-toggle]") : null;
      const closeButton = widget.querySelector("[data-assist-close]");
      const clearButton = widget.querySelector("[data-assist-clear]");
      const endpoint = widget.getAttribute("data-chat-endpoint");
      const log = widget.querySelector("[data-assist-log]");
      const form = widget.querySelector("[data-assist-form]");
      const input = widget.querySelector("[data-assist-input]");
      const sendButton = widget.querySelector("[data-assist-send]");
      const quickButtons = Array.from(widget.querySelectorAll("[data-assist-quick]"));
      const storageKey = widget.getAttribute("data-assist-storage-key") || "assist-history:user-anon";
      const maxHistoryItems = 60;
      const initialLogMarkup = log ? log.innerHTML : "";
      let historyItems = loadConversationHistory(storageKey);

      if (!endpoint || !log || !form || !input || !sendButton) {
        return;
      }

      const pushHistory = (entry) => {
        historyItems.push(entry);
        if (historyItems.length > maxHistoryItems) {
          historyItems = historyItems.slice(-maxHistoryItems);
        }
        saveConversationHistory(storageKey, historyItems);
      };

      const restoreHistory = () => {
        if (!historyItems.length) {
          return;
        }

        log.innerHTML = "";
        historyItems.forEach((entry) => {
          if (!entry || typeof entry !== "object") {
            return;
          }

          if (entry.type === "message") {
            appendMessage(log, entry.role === "user" ? "user" : "assistant", entry.text || "");
            return;
          }

          if (entry.type === "citations") {
            appendCitations(log, Array.isArray(entry.items) ? entry.items : []);
            return;
          }

          if (entry.type === "recommendations") {
            appendRecommendations(log, Array.isArray(entry.items) ? entry.items : []);
          }
        });
      };

      const resetConversation = () => {
        historyItems = [];
        clearConversationHistory(storageKey);
        log.innerHTML = initialLogMarkup;
        input.value = "";
      };

      const normalizeCitations = (items) => {
        if (!Array.isArray(items)) {
          return [];
        }
        return items.slice(0, 3).map((item) => ({
          label: item.label || "Source",
          detail: item.detail || "",
          url: item.url || "#",
        }));
      };

      const normalizeRecommendations = (items) => {
        if (!Array.isArray(items)) {
          return [];
        }
        return items.slice(0, 5).map((item) => ({
          name: item.name || "Product",
          brand: item.brand || "N/A",
          category_slug: item.category_slug || item.service || "",
          category_name: item.category_name || "",
          price: item.price || "0",
          stock: item.stock || 0,
          url: item.url || "#",
        }));
      };

      const openPanel = () => {
        widget.classList.add("is-open");
        if (toggleButton) {
          toggleButton.setAttribute("aria-expanded", "true");
        }
        window.setTimeout(() => input.focus(), 50);
      };

      const closePanel = () => {
        widget.classList.remove("is-open");
        if (toggleButton) {
          toggleButton.setAttribute("aria-expanded", "false");
          toggleButton.focus();
        }
      };

      widget.classList.remove("is-open");
      restoreHistory();
      if (toggleButton) {
        toggleButton.addEventListener("click", () => {
          if (widget.classList.contains("is-open")) {
            closePanel();
          } else {
            openPanel();
          }
        });
      }

      if (closeButton) {
        closeButton.addEventListener("click", closePanel);
      }

      if (clearButton) {
        clearButton.addEventListener("click", () => {
          resetConversation();
          if (!widget.classList.contains("is-open")) {
            openPanel();
          }
          input.focus();
        });
      }

      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && widget.classList.contains("is-open")) {
          closePanel();
        }
      });

      const currentProduct = {
        category_slug: widget.getAttribute("data-category-slug") || "",
        category_name: widget.getAttribute("data-category-name") || "",
        id: Number(widget.getAttribute("data-product-id") || 0),
        name: widget.getAttribute("data-product-name") || "",
        brand: widget.getAttribute("data-product-brand") || "",
        price: widget.getAttribute("data-product-price") || "",
      };

      const sendMessage = async (rawMessage) => {
        const message = (rawMessage || "").trim();
        if (!message) {
          return;
        }

        if (!widget.classList.contains("is-open")) {
          openPanel();
        }

        appendMessage(log, "user", message);
        pushHistory({ type: "message", role: "user", text: message });
        input.value = "";
        sendButton.disabled = true;

        const loadingNode = appendMessage(log, "assistant", "Thinking...");

        try {
          const payload = { message };
          if (currentProduct.category_slug && currentProduct.id > 0) {
            payload.current_product = currentProduct;
          }

          const response = await fetch(endpoint, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify(payload),
          });

          const data = await response.json();
          loadingNode.remove();

          if (!response.ok) {
            const errorText = data.error || "Unable to process your message right now.";
            appendMessage(log, "assistant", errorText);
            pushHistory({ type: "message", role: "assistant", text: errorText });
            return;
          }

          const answerText = data.answer || "No response generated.";
          appendMessage(log, "assistant", answerText);
          pushHistory({ type: "message", role: "assistant", text: answerText });

          const citationItems = normalizeCitations(data.citations || []);
          appendCitations(log, citationItems);
          if (citationItems.length) {
            pushHistory({ type: "citations", items: citationItems });
          }

          const recommendationItems = normalizeRecommendations(data.recommendations || []);
          appendRecommendations(log, recommendationItems);
          if (recommendationItems.length) {
            pushHistory({ type: "recommendations", items: recommendationItems });
          }
        } catch (error) {
          loadingNode.remove();
          const fallbackError = "Chat service is temporarily unavailable. Please try again.";
          appendMessage(log, "assistant", fallbackError);
          pushHistory({ type: "message", role: "assistant", text: fallbackError });
        } finally {
          sendButton.disabled = false;
          input.focus();
        }
      };

      form.addEventListener("submit", (event) => {
        event.preventDefault();
        sendMessage(input.value);
      });

      quickButtons.forEach((button) => {
        button.addEventListener("click", () => {
          const suggestion = button.getAttribute("data-assist-quick") || "";
          sendMessage(suggestion);
        });
      });
    });
  };

  const revealItems = Array.from(document.querySelectorAll("[data-reveal]"));
  if (revealItems.length) {
    const revealAboveFold = () => {
      revealItems.forEach((item) => {
        const top = item.getBoundingClientRect().top;
        if (top < window.innerHeight * 0.92) {
          item.classList.add("is-visible");
        }
      });
    };

    revealAboveFold();

    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.12 }
      );
      revealItems.forEach((item) => observer.observe(item));

      // Final safeguard: never keep content hidden if observer events are delayed.
      window.setTimeout(() => {
        revealItems.forEach((item) => item.classList.add("is-visible"));
      }, 650);
    } else {
      revealItems.forEach((item) => item.classList.add("is-visible"));
    }
  }

  const mainImage = document.getElementById("detail-main-image");
  const thumbButtons = Array.from(document.querySelectorAll("[data-gallery-thumb]"));
  if (mainImage && thumbButtons.length) {
    thumbButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const imageUrl = button.getAttribute("data-image");
        if (!imageUrl) {
          return;
        }
        mainImage.src = imageUrl;
        thumbButtons.forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
      });
    });
  }

  const shareButton = document.querySelector("[data-share-url]");
  if (shareButton) {
    shareButton.addEventListener("click", async () => {
      const shareUrl = shareButton.getAttribute("data-share-url");
      if (!shareUrl) {
        return;
      }

      if (navigator.share) {
        try {
          await navigator.share({
            title: document.title,
            url: shareUrl,
          });
          return;
        } catch (error) {
          // If sharing is cancelled, silently continue to clipboard fallback.
        }
      }

      if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(shareUrl);
          shareButton.textContent = "Link Copied";
          window.setTimeout(() => {
            shareButton.textContent = "Share";
          }, 1300);
          return;
        } catch (error) {
          // Keep the prompt fallback below for strict browser contexts.
        }
      }

      window.prompt("Copy this product link:", shareUrl);
    });
  }

  initChatbotWidgets();
})();

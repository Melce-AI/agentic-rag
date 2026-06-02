# Qdrant Mesafe Metrikleri Rehberi (Distance Metrics Guide)

Qdrant, vektör benzerliği hesaplamak için çeşitli mesafe metriklerini destekler. Doğru metriği seçmek, modelinizin performansını ve doğruluğunu doğrudan etkiler.

---

## 📏 1. Temel Metrikler ve Kullanım Senaryoları

| Metrik | Teknik Adı | Ne Ölçer? | En İyi Kullanım Zamanı |
| :--- | :--- | :--- | :--- |
| **Cosine Similarity** | `Cosine` | İki vektör arasındaki açıyı ölçer. Vektör uzunluğunu ihmal eder. | **RAG, Metin Benzerliği, NLP.** |
| **Euclidean Distance** | `Euclid` | İki nokta arasındaki en kısa "kuş uçuşu" mesafeyi ölçer. | **Fiziksel veriler, Görüntü işleme, Boyutun önemli olduğu durumlar.** |
| **Dot Product** | `Dot` | İki vektörün hizalanmasını ve büyüklüklerini çarparak toplar. | **Öneri sistemleri, Ölçekli (scaled) embedding'ler.** |
| **Manhattan Distance** | `Manhattan` | Izgara şeklinde (sadece dikey ve yatay) toplam mesafeyi ölçer. | **Yüksek boyutlu seyrek veriler, Aykırı değer (outlier) direnci.** |

---

## 🧩 2. Detaylı İnceleme

### 🔹 Cosine Similarity (Kosinüs Benzerliği) - *Varsayılan*
*   **Nedir?** Vektörlerin büyüklüklerini (uzunluklarını) 1'e normalize eder ve sadece aralarındaki açıya bakar.
*   **Neden kullanmalısın?** Kelime sayısı farklı olan iki dokümanın (biri kısa, biri uzun) aynı konudan bahsediyorsa benzer çıkmasını sağlar. 
*   **Senaryo:** "Ankara'da hava durumu" ile "Bugün Ankara'da hava nasıl olacak?" cümlelerinin birbirine yakın çıkması için idealdir.

### 🔹 Euclidean Distance (L2 - Öklid Mesafesi)
*   **Nedir?** Bildiğimiz geometrik mesafedir. Vektörlerin büyüklüğü önemlidir.
*   **Püf Noktası:** Eğer verileriniz normalize edilmemişse, büyük değerler küçükleri domine edebilir. Genelde vektörel olmayan fiziksel özelliklerde kullanılır.
*   **Senaryo:** Boy, kilo, yaş gibi sayısal sütunlardan oluşturulmuş bir vektörde aradaki farkın büyüklüğü anlamlıysa kullanılır.

### 🔹 Dot Product (Nokta Çarpımı)
*   **Nedir?** Vektörlerin büyüklüğü ve yönünü birleştirir.
*   **Püf Noktası:** Eğer vektörler normalize edilmişse (Cosine gibi), Dot Product matematiksel olarak Cosine ile aynıdır ancak daha hızlı hesaplanır.
*   **Senaryo:** Bir kullanıcının ilgi düzeyi (vektör boyu) ve ürünün özelliği (yön) birleşip "skor" oluşturuyorsa (Recommendation Engine) tercih edilir.

### 🔹 Manhattan Distance (L1 - Taksi Mesafesi)
*   **Nedir?** Kareli bir kağıt üzerinde bir noktadan diğerine gitmek gibi düşünün. Çapraz gidiş yoktur.
*   **Neden kullanmalısın?** Euclidean'a göre "outlier" (uç değerlere) çok daha dirençlidir. Boyut sayısı arttıkça Euclidean'dan daha iyi sonuç verebilir.

---

## ⚡ 3. Sparse (Seyrek) Vektörler ve BM25

Projemizde kullandığımız `sparse-text` alanı için Qdrant genellikle **Dot Product** kullanır. Ancak modern kurulumlarda:

- **BM25:** Kelime frekansına dayalı geleneksel arama sistemidir. Qdrant v1.15+ ile sunucu tarafında IDF hesaplayarak BM25 skorlaması yapabilir.
- **SPLADE:** Yapay zeka ile zenginleştirilmiş sparse vektörlerdir. "Benzer" kelimeleri otomatik ekler (expansion).

---

## Hangisini Seçmeliyim?

1.  **Metin/PDF arıyorsan (RAG):** Düşünme, **`Distance.COSINE`** kullan. Çoğu embedding modeli (MiniLM, OpenAI, Cohere) buna göre eğitilmiştir.
2.  **Ürün önerisi yapıyorsan:** Eğer popülerlik (vektör boyu) önemliyse **`Dot Product`** kullan.
3.  **Fiziksel ölçüm (konum, sensör):** **`Euclidean`** kullan.
4.  **Hız çok kritikse:** Vektörlerini önden normalize et ve **`Dot Product`** kullan (Cosine hızında aynı sonucu verir).

---

> [!TIP]
> Mevcut kodumuzda `src/adapters/vector_store/qdrant.py` içerisinde `Distance.COSINE` kullanıyoruz. RAG sistemimiz için en doğru seçim budur.

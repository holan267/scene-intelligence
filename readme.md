Nếu phân loại theo mục đích sử dụng, đây là những thư viện AI nổi tiếng và được sử dụng nhiều nhất hiện nay:

## 1. Machine Learning truyền thống

| Thư viện     | Ngôn ngữ   | Mục đích                               |
| ------------ | ---------- | -------------------------------------- |
| Scikit-learn | Python     | Classification, Regression, Clustering |
| XGBoost      | Python/C++ | Gradient Boosting hiệu năng cao        |
| LightGBM     | Python/C++ | Gradient Boosting cho dữ liệu lớn      |
| CatBoost     | Python     | Xử lý categorical data tốt             |

---

## 2. Deep Learning

| Thư viện   | Điểm mạnh                                           |
| ---------- | --------------------------------------------------- |
| PyTorch    | Framework phổ biến nhất trong nghiên cứu AI         |
| TensorFlow | Mạnh cho production và mobile                       |
| Keras      | API đơn giản để xây dựng neural network             |
| JAX        | Tính toán tốc độ cao, được nhiều công ty AI sử dụng |

---

## 3. Large Language Models (LLM)

Đây là nhóm thư viện rất phổ biến từ năm 2023 đến nay.

| Thư viện     | Công dụng                          |
| ------------ | ---------------------------------- |
| Transformers | Load và chạy hàng nghìn mô hình AI |
| vLLM         | Inference LLM tốc độ cao           |
| llama.cpp    | Chạy LLM trên CPU                  |
| Ollama       | Chạy AI local cực dễ               |
| MLX          | Chạy AI trên Apple Silicon         |

---

## 4. AI Agent Framework

Các framework giúp xây dựng AI Agent.

| Thư viện        | Điểm mạnh                        |
| --------------- | -------------------------------- |
| LangChain       | Framework phổ biến nhất          |
| LlamaIndex      | Kết nối dữ liệu với LLM          |
| AutoGen         | Multi-Agent                      |
| CrewAI          | Xây dựng nhiều agent cộng tác    |
| Semantic Kernel | Tích hợp AI vào ứng dụng .NET/C# |
| PydanticAI      | Framework hiện đại, type-safe    |

---

## 5. RAG (Retrieval-Augmented Generation)

| Thư viện   | Mục đích        |
| ---------- | --------------- |
| LlamaIndex | RAG phổ biến    |
| Haystack   | Enterprise RAG  |
| LangChain  | Pipeline RAG    |
| txtai      | Semantic Search |

---

## 6. Vector Database

Không phải thư viện AI thuần túy nhưng gần như luôn đi kèm AI.

| Công nghệ | Mục đích             |
| --------- | -------------------- |
| FAISS     | Vector Search        |
| Chroma    | Local Vector DB      |
| Milvus    | Enterprise Vector DB |
| Qdrant    | Hiệu năng cao        |
| Weaviate  | Hybrid Search        |

---

## 7. Computer Vision

| Thư viện    | Công dụng                 |
| ----------- | ------------------------- |
| OpenCV      | Xử lý ảnh, video          |
| Ultralytics | Object Detection (YOLO)   |
| Detectron2  | Detection & Segmentation  |
| MediaPipe   | Face, Hand, Pose Tracking |

---

## 8. Speech AI

| Thư viện    | Công dụng         |
| ----------- | ----------------- |
| Whisper     | Speech to Text    |
| Coqui TTS   | Text to Speech    |
| SpeechBrain | Speech Processing |

---

## 9. AI Deployment

| Thư viện     | Mục đích               |
| ------------ | ---------------------- |
| ONNX Runtime | Chạy model đa nền tảng |
| TensorRT     | Tối ưu GPU NVIDIA      |
| TorchServe   | Deploy PyTorch         |

---

## 10. Nếu bạn dùng .NET/C#

Đây là các thư viện đáng chú ý:

* Semantic Kernel
* Microsoft.Extensions.AI
* ML.NET
* ONNX Runtime
* Azure AI Foundry SDK

### Gợi ý theo nhu cầu

* **Muốn học AI/ML cơ bản:** Scikit-learn → PyTorch.
* **Muốn phát triển ứng dụng AI dùng LLM:** Transformers + LangChain hoặc LlamaIndex.
* **Muốn xây dựng AI Agent:** Semantic Kernel (đặc biệt nếu dùng .NET), AutoGen, CrewAI hoặc PydanticAI.
* **Muốn xây dựng hệ thống RAG:** LlamaIndex + FAISS/Chroma/Qdrant.
* **Muốn chạy mô hình cục bộ:** Ollama, llama.cpp hoặc vLLM (cho máy chủ GPU).
* **Làm việc với C#/.NET:** Semantic Kernel kết hợp Microsoft.Extensions.AI đang là một trong những lựa chọn hiện đại và được Microsoft đầu tư mạnh.

Stack bạn liệt kê là một pipeline AI khá điển hình cho **phân tích video (video understanding)**. Dưới đây là phân tích vai trò của từng thư viện/mô hình và đánh giá.

| Thành phần                             | Thư viện/Mô hình            | Vai trò                                                                        | Đánh giá                                                      |
| -------------------------------------- | --------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| **Scene Splitting**                    | PySceneDetect               | Tách video thành các scene dựa trên thay đổi hình ảnh                          | ⭐⭐⭐⭐⭐ Tiêu chuẩn thực tế, nhanh và ổn định                    |
| **Speech-to-Text**                     | Faster Whisper (`large-v3`) | Chuyển lời nói thành văn bản                                                   | ⭐⭐⭐⭐⭐ Rất chính xác, nhanh hơn Whisper gốc nhiều lần          |
| **Face Recognition**                   | InsightFace (`buffalo_l`)   | Phát hiện, căn chỉnh và nhận diện khuôn mặt                                    | ⭐⭐⭐⭐⭐ Một trong những lựa chọn tốt nhất hiện nay              |
| **Visual Embedding**                   | SigLIP 2                    | Sinh embedding biểu diễn nội dung hình ảnh để tìm kiếm hoặc RAG đa phương thức | ⭐⭐⭐⭐⭐ Mạnh hơn nhiều mô hình CLIP đời cũ trong nhiều bài toán |
| **Object Detection**                   | YOLOE                       | Phát hiện các đối tượng trong khung hình                                       | ⭐⭐⭐⭐☆ Hiệu năng tốt, phù hợp xử lý thời gian thực             |
| **Shot Scale**                         | ResNet (ResNet50)           | Phân loại cỡ cảnh quay (Close-up, Medium, Wide...)                             | ⭐⭐⭐☆ Phụ thuộc chất lượng dữ liệu huấn luyện                  |
| **OCR**                                | EasyOCR + VietOCR           | Nhận dạng văn bản trong video, đặc biệt tiếng Việt                             | ⭐⭐⭐⭐⭐ Kết hợp này rất phù hợp cho video tiếng Việt            |
| **Summarization & Keyword Extraction** | Qwen (Qwen3.5-9B-Q8)        | Tóm tắt nội dung và trích xuất từ khóa                                         | ⭐⭐⭐⭐⭐ Rất mạnh nếu chạy cục bộ hoặc trên GPU                  |

## Pipeline tổng thể

```text
Video
   │
   ▼
PySceneDetect
   │
   ├──────── Scene 1
   ├──────── Scene 2
   └──────── ...
        │
        ▼
Frame Sampling
        │
        ├────────► YOLOE
        │
        ├────────► InsightFace
        │
        ├────────► EasyOCR/VietOCR
        │
        ├────────► SigLIP2 Embedding
        │
        └────────► Shot Scale (ResNet50)

Audio
        │
        ▼
Faster Whisper
        │
        ▼
Transcript
        │
        ▼
Qwen3.5
        │
        ├────────► Summary
        ├────────► Keywords
        └────────► Scene Description
```

## Dữ liệu đầu ra có thể thu được

Sau khi xử lý mỗi scene, bạn có thể lưu:

```json
{
  "scene_id": 12,
  "start": "00:03:15",
  "end": "00:03:42",
  "transcript": "...",
  "summary": "...",
  "keywords": [
    "World Cup",
    "Messi",
    "Goal"
  ],
  "faces": [
    "Person A",
    "Person B"
  ],
  "objects": [
    "car",
    "microphone",
    "stadium"
  ],
  "ocr": [
    "Breaking News",
    "Vietnam"
  ],
  "shot_scale": "Close-up",
  "embedding": [ ... ]
}
```

Dữ liệu này rất phù hợp để:

* Xây dựng **semantic search** theo nội dung video.
* Thực hiện **RAG đa phương thức** (kết hợp văn bản và hình ảnh).
* Tìm kiếm theo người, đối tượng, văn bản xuất hiện trên màn hình hoặc câu thoại.
* Tự động tạo metadata cho hệ thống quản lý tài sản số (MAM/DAM).

## Đánh giá tổng thể

Đây là một stack hiện đại và phù hợp cho hệ thống phân tích video, đặc biệt với video tin tức hoặc truyền hình:

* **PySceneDetect**: chuẩn cho tách cảnh.
* **Faster Whisper large-v3**: rất mạnh cho nhận dạng giọng nói.
* **InsightFace buffalo_l**: lựa chọn hàng đầu về nhận diện khuôn mặt.
* **SigLIP2**: embedding hình ảnh chất lượng cao cho tìm kiếm ngữ nghĩa.
* **YOLOE**: phát hiện đối tượng nhanh và hiệu quả.
* **EasyOCR + VietOCR**: kết hợp tốt cho nội dung tiếng Việt.
* **Qwen3.5-9B**: đủ mạnh để tóm tắt, sinh mô tả và trích xuất từ khóa.

Nếu mục tiêu của bạn là xây dựng một hệ thống **AI Video Indexing** hoặc **Media Asset Management (MAM)** tương tự các giải pháp của Google Video Intelligence, Azure Video Indexer hoặc AWS Rekognition Video, thì pipeline này là một nền tảng rất hợp lý và có thể mở rộng thêm các tác vụ như nhận diện logo, phân tích hành động, nhận diện cảm xúc hoặc captioning đa phương thức.

Tài liệu bạn gửi mô tả toàn bộ khả năng của **Amazon Rekognition Video**. Nếu so sánh với pipeline AI mà bạn đang xây dựng thì có thể thấy AWS đã triển khai gần như đầy đủ các thành phần của một hệ thống **Video Intelligence**. ([AWS Documentation][1])

## So sánh pipeline của bạn với Amazon Rekognition

| Chức năng                   | Pipeline của bạn        | Amazon Rekognition Video          |
| --------------------------- | ----------------------- | --------------------------------- |
| Scene splitting             | ✅ PySceneDetect         | ✅ Video Segments (Shot Detection) |
| Object Detection            | ✅ YOLOE                 | ✅ Label Detection                 |
| Face Detection              | ✅ InsightFace           | ✅ Face Detection                  |
| Face Recognition            | ✅ InsightFace buffalo_l | ✅ Face Search (Collection)        |
| Celebrity Recognition       | ❌                       | ✅                                 |
| Person Tracking             | Có thể bổ sung          | ✅                                 |
| OCR                         | ✅ EasyOCR + VietOCR     | ✅ Text Detection                  |
| Speech-to-Text              | ✅ Faster Whisper        | ❌ Không hỗ trợ STT                |
| Image Embedding             | ✅ SigLIP2               | ❌ Không có                        |
| Video Search bằng Embedding | ✅ Có thể xây dựng       | ❌ Không có                        |
| Summarization               | ✅ Qwen                  | ❌ Không có                        |
| Keyword Extraction          | ✅ Qwen                  | ❌ Không có                        |
| Unsafe Content              | Chưa có                 | ✅ Moderation                      |
| Activity Recognition        | Một phần qua YOLO       | ✅ Labels + Activities             |

---

## Những khả năng Rekognition có

### 1. Video Segments (Shot Detection)

Đây là tính năng tương tự **PySceneDetect**, nhưng được AWS triển khai dưới dạng dịch vụ cloud.

Rekognition tự động phát hiện:

* Shot boundaries
* Black frames
* Opening credits
* End credits
* Color bars
* Slates

Điểm mạnh là không chỉ cắt scene mà còn phân loại loại segment. ([AWS Documentation][2])

---

### 2. Label Detection

Khác với YOLO chỉ detect object.

Rekognition detect:

* Objects
* Scenes
* Concepts
* Activities

Ví dụ:

```
Car
Road
Building
Office
Microphone
Football
Running
Swimming
```

và trả về:

```
Timestamp
Confidence
Bounding Box
Parents
Aliases
```

Điều này gần giống:

```
YOLO
+
ImageNet Classification
+
Activity Classification
```

([AWS Documentation][3])

---

### 3. Person Tracking

Đây là tính năng khá hay.

AWS không chỉ detect người.

Nó còn:

```
Person #1

Frame 100
↓

Frame 101
↓

Frame 102
↓

Frame 500
```

và giữ nguyên ID.

YOLO thông thường không làm việc này.

Nếu muốn tương đương bạn sẽ cần:

```
YOLOE

+

ByteTrack

hoặc

BoT-SORT

hoặc

DeepSORT
```

---

### 4. Face Search

InsightFace của bạn làm được tương tự.

Pipeline:

```
Face Detection

↓

Embedding

↓

Vector Search

↓

Identity
```

AWS dùng:

```
Collection

↓

IndexFaces()

↓

StartFaceSearch()

↓

GetFaceSearch()
```

Ý tưởng gần như giống hệt.

([AWS Documentation][1])

---

### 5. OCR

AWS detect:

* subtitle
* biển báo
* banner
* logo text
* lower-third

Điều này tương đương:

```
EasyOCR

+

VietOCR
```

---

## Những gì pipeline của bạn mạnh hơn AWS

Đây là điểm mình thấy đáng chú ý.

### 1. Speech Understanding

AWS:

```
Video only
```

Bạn:

```
Video

+

Whisper
```

Nghĩa là bạn hiểu được:

* lời dẫn
* hội thoại
* phỏng vấn
* tin tức

---

### 2. Semantic Embedding

AWS không sinh embedding.

Bạn có:

```
SigLIP2

↓

768/1024 dimensions

↓

Vector DB

↓

Semantic Search
```

Ví dụ:

"Tìm cảnh có người đang phỏng vấn ngoài trời"

→ embedding sẽ tìm được dù không có keyword.

---

### 3. LLM

AWS chỉ trả về:

```
Person

Car

Tree

Office
```

Trong khi Qwen có thể sinh:

```
"Cảnh phỏng vấn diễn ra tại sân vận động.

Một người đàn ông cầm micro đang trả lời báo chí."
```

Đây là metadata giàu ngữ nghĩa hơn rất nhiều.

---

### 4. RAG

Pipeline của bạn có thể:

```
Video

↓

Metadata

↓

Embedding

↓

Vector DB

↓

LLM

↓

Chat with Video
```

AWS Rekognition không cung cấp khả năng này.

---

## Kiến trúc tổng thể đề xuất

```text
                Video
                  │
     ┌────────────┴────────────┐
     │                         │
  Video Frames              Audio
     │                         │
PySceneDetect          Faster Whisper
     │                         │
     │                  Transcript
     │                         │
     ├──── YOLOE
     ├──── InsightFace
     ├──── EasyOCR/VietOCR
     ├──── SigLIP2
     ├──── Shot Scale
     └──── (ByteTrack)
                  │
                  ▼
        Scene Metadata JSON
                  │
        ┌─────────┴─────────┐
        │                   │
     Qwen3.5            Vector DB
        │                   │
  Summary / Keywords    Embeddings
        └─────────┬─────────┘
                  ▼
          Search / RAG / Chat
```

## Đánh giá

Nếu xem **Amazon Rekognition Video** là một chuẩn tham chiếu, thì pipeline của bạn đã bao phủ hầu hết các năng lực cốt lõi về phân tích video và còn mở rộng thêm các khả năng mà Rekognition không có:

* **Tương đương Rekognition:** tách cảnh, phát hiện đối tượng, OCR, nhận diện khuôn mặt.
* **Vượt Rekognition:** nhận dạng giọng nói (Whisper), embedding đa phương thức (SigLIP2), tóm tắt và trích xuất từ khóa (Qwen), tìm kiếm ngữ nghĩa và RAG.
* **Có thể bổ sung để ngang hoặc vượt Rekognition hơn nữa:**

  * Theo dõi đối tượng/người bằng **ByteTrack** hoặc **BoT-SORT**.
  * Nhận diện hành động bằng các mô hình như **VideoMAE**, **InternVideo2** hoặc **X-CLIP**.
  * Nhận diện logo bằng **Grounding DINO** hoặc mô hình fine-tuned.
  * Sinh mô tả video tự động (video captioning) bằng các mô hình đa phương thức như **Qwen2.5-VL** hoặc **InternVL**.

Với các bổ sung này, hệ thống sẽ tiến gần đến các nền tảng **Video Intelligence** thương mại như Amazon Rekognition, nhưng vẫn giữ được lợi thế là chạy on-premise và có thể tùy biến sâu cho bài toán MAM hoặc truyền hình.

[1]: https://docs.aws.amazon.com/rekognition/latest/dg/video.html?utm_source=chatgpt.com "Working with stored video analysis operations - Amazon Rekognition"
[2]: https://docs.aws.amazon.com/rekognition/?utm_source=chatgpt.com "Amazon Rekognition Documentation"
[3]: https://docs.aws.amazon.com/rekognition/latest/dg/how-it-works.html?utm_source=chatgpt.com "How Amazon Rekognition works - Amazon Rekognition"
Đối với hệ thống giống **AWS Rekognition**, **Azure Video Indexer** hay **Google Video Intelligence**, cách lưu metadata quan trọng hơn việc chọn model. Thực tế, các hệ thống này đều lưu **metadata theo từng scene (hoặc shot)** và coi scene là đơn vị nhỏ nhất có ý nghĩa để tìm kiếm.

## Kiến trúc nên dùng

Thay vì lưu theo video:

```
Video
    └── Metadata
```

nên lưu theo:

```
Video
    ├── Scene 1
    ├── Scene 2
    ├── Scene 3
    └── ...
```

Mỗi scene có đầy đủ metadata và embedding riêng.

---

# 1. Metadata của Scene

Ví dụ:

```json
{
  "scene_id": "scene_0012",
  "video_id": "video_news_20260702",

  "start_ms": 185000,
  "end_ms": 198500,

  "duration": 13.5,

  "shot_scale": "Close Up",

  "transcript": "...",

  "summary": "...",

  "keywords": [
    "Prime Minister",
    "Meeting",
    "Vietnam"
  ],

  "faces": [
    {
      "person_id": "123",
      "name": "Nguyen Van A",
      "confidence": 0.99
    }
  ],

  "objects": [
    {
      "label": "Car",
      "confidence": 0.96
    },
    {
      "label": "Microphone",
      "confidence": 0.98
    }
  ],

  "ocr": [
    "VTV1",
    "Breaking News"
  ],

  "location": "Conference Room",

  "emotion": [
      "neutral"
  ],

  "visual_embedding": [...],

  "text_embedding": [...],

  "scene_embedding": [...]
}
```

---

# 2. Nên lưu vào đâu?

Thông thường sẽ kết hợp **3 loại storage**.

## PostgreSQL

Lưu metadata có cấu trúc.

```
Scene

VideoId

Start

End

Duration

Summary

Transcript

JSON Metadata
```

Ví dụ:

```
Scene
---------
Id

VideoId

StartMs

EndMs

Summary

Transcript

Metadata(JSONB)
```

JSONB chứa

```
Objects

Faces

OCR

Keywords

Emotion
```

Ưu điểm

* filter nhanh
* SQL mạnh

---

## Vector Database

Ví dụ:

* Qdrant
* Milvus
* Weaviate
* pgvector

Mỗi Scene có một vector.

```
Scene 1

embedding
↓

[0.34,
0.81,
...]

payload

scene_id
video_id
start
end
summary
```

---

## Object Storage

Video gốc

```
S3

MinIO

NAS
```

---

# 3. Có bao nhiêu embedding?

Khuyến nghị **3 embedding**.

## Visual Embedding

Từ SigLIP2

Đại diện nội dung hình ảnh.

Ví dụ

```
Man speaking

↓

vector
```

---

## Text Embedding

Từ transcript.

Ví dụ

```
"Thủ tướng phát biểu..."

↓

embedding
```

---

## Scene Embedding

Đây là quan trọng nhất.

Ghép

```
Summary

+

Transcript

+

OCR

+

Object Labels

+

Face Names
```

Ví dụ

```
Summary

"Prime Minister speaking at conference"

OCR

"Vietnam Summit"

Objects

Microphone

Podium

Audience

Faces

Pham Minh Chinh
```

đưa toàn bộ vào model embedding.

Sinh ra

```
Scene Embedding
```

Đây là vector sẽ dùng để search.

---

# 4. Search bằng ngôn ngữ tự nhiên

Ví dụ user nhập

```
"Tìm cảnh Thủ tướng phát biểu trước báo chí"
```

Pipeline

```
Query

↓

Embedding

↓

Vector Search

↓

Top K Scene

↓

Return Scene
```

Không cần keyword.

---

Ví dụ khác

```
"Tìm cảnh có ô tô chạy trên cầu"

↓

Embedding

↓

Scene #25
```

Mặc dù transcript không hề có chữ "ô tô".

---

# 5. Hybrid Search (rất nên dùng)

Không chỉ dùng vector.

Kết hợp

```
Natural Language

↓

Embedding

↓

Vector Search

+

SQL Filter

+

BM25

↓

Re-ranking
```

Ví dụ

```
"Tìm cảnh Messi ghi bàn trong hiệp hai"

↓

Filter

Player = Messi

↓

Transcript contains

Goal

↓

Embedding

↓

Top 20

↓

Rerank

↓

Top 5
```

Đây là cách hầu hết hệ thống enterprise hoạt động.

---

# 6. Metadata có nên lưu object không?

Có.

Ví dụ

```
Objects

Car

0.92

Frame 10

Frame 11

Frame 12
```

Nhưng nên gom.

```
Scene

Objects

Car

Dog

Person

Microphone
```

Không cần lưu 300 frame.

Chỉ lưu

```
First Seen

Last Seen

Max Confidence
```

là đủ.

---

# 7. Có nên dùng LLM sinh Summary?

Rất nên.

Ví dụ Scene

```
Transcript

"Xin chào quý vị..."

Objects

Desk

Monitor

Person

OCR

VTV1
```

Qwen sinh

```
Một người dẫn chương trình đang đọc bản tin trong trường quay VTV.
```

Sau đó embedding câu này.

Kết quả search sẽ chính xác hơn rất nhiều.

---

# 8. Kiến trúc hoàn chỉnh

```text
                 Video
                   │
         PySceneDetect
                   │
      ┌────────────┴────────────┐
      │                         │
   Audio                    Frames
      │                         │
Whisper                  YOLOE
      │                  InsightFace
Transcript               OCR
      │                  SigLIP2
      └──────────┬──────────────┘
                 ▼
           Scene Metadata
                 │
      ┌──────────┴──────────┐
      │                     │
   PostgreSQL           Vector DB
 (JSONB + Index)      (Scene Embedding)
      │                     │
      └──────────┬──────────┘
                 ▼
          Hybrid Search API
                 │
       Natural Language Query
                 │
      Vector Search + Filters
                 │
             Re-ranking
                 │
          Scene + Timestamp
```

### Khuyến nghị cho dự án của bạn

Với stack hiện tại (**PySceneDetect + Faster Whisper + InsightFace + SigLIP2 + YOLOE + OCR + Qwen**), mình khuyên nên thiết kế theo hướng **metadata giàu ngữ nghĩa (semantic metadata)** thay vì chỉ lưu kết quả thô của từng mô hình:

* **PostgreSQL + JSONB**: lưu metadata có cấu trúc (scene, transcript, OCR, object, face, timestamps, confidence...).
* **pgvector** (nếu quy mô vừa) hoặc Qdrant (nếu quy mô lớn): lưu **một embedding tổng hợp cho mỗi scene**.
* **Qwen**: tạo `scene_description` dài 2–5 câu và `keywords` chuẩn hóa trước khi embedding.
* **Hybrid Search**: kết hợp **vector search** với **lọc metadata** (theo người, thời gian, loại đối tượng, kênh, chương trình...) rồi dùng một **reranker** (ví dụ mô hình BGE Reranker hoặc Qwen ở chế độ rerank) để sắp xếp lại kết quả.

Đây là kiến trúc mà nhiều hệ thống Video AI hiện đại áp dụng vì vừa hỗ trợ truy vấn ngôn ngữ tự nhiên như *"cảnh phóng viên phỏng vấn ngoài trời có logo VTV1"* vừa cho phép lọc chính xác theo các điều kiện nghiệp vụ.

Tài liệu của **Azure Video Indexer** rất đáng tham khảo vì đây là một trong những hệ thống Video AI hoàn chỉnh nhất hiện nay. Nếu so sánh với pipeline của bạn, có thể thấy Microsoft không chỉ chạy nhiều model AI mà còn xây dựng một **knowledge graph của video**. Đây là điểm đáng học hỏi hơn là bản thân các model.

## Kiến trúc của Azure Video Indexer

Thay vì chỉ sinh metadata:

```text
Video
    ↓
Objects
Faces
OCR
Transcript
```

Azure tạo nhiều lớp thông tin:

```text
Video
    ↓
Insights
    ↓
Scenes
    ↓
Shots
    ↓
Keyframes
    ↓
AI Metadata
    ↓
Search Index
```

Tức là mỗi video được biểu diễn như một tập các thực thể (entities) và mối quan hệ giữa chúng.

---

# Những AI mà Azure Video Indexer sử dụng

Theo tài liệu, Video Indexer có các nhóm tính năng sau:

| Nhóm      | Tính năng                                   |
| --------- | ------------------------------------------- |
| Speech    | Speech-to-Text, Speaker Identification      |
| Vision    | Faces, People, OCR, Objects                 |
| Video     | Shot Detection, Scene Detection, Keyframes  |
| NLP       | Keywords, Named Entities, Topics, Sentiment |
| Knowledge | Brands, Locations, Celebrities              |
| Search    | Timeline Search                             |
| Summary   | Automatic Summary                           |

Bạn có thể thấy pipeline hiện tại của bạn đã bao phủ khoảng **80–90%** các năng lực cốt lõi.

---

# Điều Azure làm rất hay

## 1. Scene → Shot → Keyframe

Đây là điều mình khuyên bạn nên áp dụng.

Đừng chỉ có Scene.

Nên có:

```text
Video

↓

Scene

↓

Shot

↓

Representative Keyframe
```

Ví dụ

```text
Scene

00:10-00:40

↓

Shot 1

00:10-00:20

↓

Shot 2

00:20-00:30

↓

Shot 3

00:30-00:40
```

Sau đó chỉ chạy

* SigLIP2
* YOLO
* InsightFace
* OCR

trên **Keyframe**

thay vì toàn bộ frame.

Tiết kiệm GPU rất nhiều.

---

## 2. Timeline Metadata

Azure lưu mọi thứ theo thời gian.

Ví dụ

```json
{
    "object":"Car",
    "appear":[
        {
            "start":"00:01:23",
            "end":"00:01:40"
        }
    ]
}
```

Face cũng vậy.

OCR cũng vậy.

Speaker cũng vậy.

Đây là điểm rất quan trọng.

---

# Không nên chỉ lưu

```json
{
    "objects":[
        "Car",
        "Person"
    ]
}
```

Mà nên

```json
{
    "objects":[
        {
            "label":"Car",
            "confidence":0.96,
            "start":81,
            "end":93
        }
    ]
}
```

---

# 3. Metadata nhiều tầng

Azure không chỉ có Summary.

Ví dụ

```
Transcript

↓

Keywords

↓

Topics

↓

Named Entity

↓

Summary
```

Ví dụ

Transcript

```
Hôm nay Thủ tướng...

```

↓

Keywords

```
Prime Minister

Conference

Vietnam
```

↓

Entities

```
Pham Minh Chinh

Hanoi

Government
```

↓

Summary

```
Prime Minister attended...
```

Đây chính là dữ liệu để search.

---

# 4. Knowledge Graph

Azure coi video là tập entity.

Ví dụ

```
Scene

↓

Face

↓

Person

↓

Object

↓

OCR

↓

Topic

↓

Location

↓

Emotion
```

Tất cả liên kết với nhau.

Ví dụ

```
Scene 25

↓

Face

↓

Messi

↓

Object

↓

Football

↓

Location

↓

Stadium
```

Lúc này search

```
Messi playing football
```

không cần transcript.

---

# 5. Search

Azure không search transcript.

Nó search

```
Transcript

+

OCR

+

Objects

+

Faces

+

Keywords

+

Topics

+

Summary
```

Sau đó hợp nhất kết quả.

Đây gọi là **Hybrid Search**.

---

# Nếu mình thiết kế lại pipeline

Mình sẽ thêm một tầng gọi là **Scene Intelligence**.

```
Video

↓

Scene Detection

↓

Shot Detection

↓

Representative Frame

↓

Object Detection

↓

OCR

↓

Face Recognition

↓

Visual Embedding

↓

Speech-to-Text

↓

LLM

↓

Scene Intelligence
```

Scene Intelligence có dạng

```json
{
    "scene_description":"",
    "objects":[],
    "faces":[],
    "ocr":[],
    "keywords":[],
    "summary":"",
    "entities":[],
    "embedding":[]
}
```

Đây mới là dữ liệu đem đi search.

---

# Kiến trúc mình khuyên nếu bạn muốn đạt mức Azure Video Indexer

```text
                Video
                   │
          Scene Detection
                   │
            Shot Detection
                   │
      Representative Keyframe
                   │
        ┌──────────┼──────────┐
        │          │          │
      YOLO     InsightFace   OCR
        │          │          │
        └──────────┼──────────┘
                   │
             SigLIP2 Embedding
                   │
              Whisper Transcript
                   │
             Qwen Scene Summary
                   │
        Entity Extraction / Topics
                   │
        Scene Intelligence JSON
          ├── PostgreSQL (metadata)
          ├── pgvector / Qdrant (embeddings)
          └── Elasticsearch / OpenSearch (BM25)
                   │
              Hybrid Search API
                   │
         NL Query → Retrieve → Rerank
                   │
        Scene + Timestamp + Thumbnail
```

## Khuyến nghị bổ sung

Nếu mục tiêu của bạn là xây dựng một hệ thống MAM/Video Search tương đương Azure Video Indexer cho môi trường on-premise, mình sẽ bổ sung thêm vài thành phần ngoài stack hiện tại:

| Chức năng                                    | Đề xuất                       |
| -------------------------------------------- | ----------------------------- |
| Speaker diarization (ai đang nói)            | pyannote.audio                |
| Entity extraction (người, địa điểm, tổ chức) | GLiNER hoặc dùng Qwen         |
| Reranking kết quả tìm kiếm                   | BGE Reranker                  |
| Full-text + BM25                             | OpenSearch hoặc Elasticsearch |
| Vector search                                | Qdrant hoặc pgvector          |

Điểm quan trọng nhất rút ra từ Azure Video Indexer là: **đừng coi transcript, object hay OCR là kết quả cuối cùng**. Hãy coi chúng là các "tín hiệu" để xây dựng một **Scene Intelligence** giàu ngữ nghĩa. Sau đó tạo một **scene embedding tổng hợp**, kết hợp với tìm kiếm full-text và metadata filter. Đây là cách để hỗ trợ các truy vấn tự nhiên như:

* "Tìm cảnh người dẫn chương trình đứng trước màn hình thời tiết."
* "Cảnh có logo VTV và một chiếc xe cứu hỏa."
* "Đoạn Thủ tướng phát biểu về kinh tế tại Hà Nội."

mà vẫn trả về đúng **scene**, **timestamp** và **thumbnail** với độ chính xác cao.

Đây là phần quan trọng nhất của một hệ thống Video Search. Các hệ thống như **Azure Video Indexer**, **Microsoft Copilot**, **Google Vertex AI Search** hay các hệ thống RAG hiện đại đều không chỉ dùng vector search mà dùng **Hybrid Search**.

## Ý tưởng

Một câu hỏi bằng ngôn ngữ tự nhiên chứa nhiều loại thông tin khác nhau.

Ví dụ:

> "Tìm cảnh Thủ tướng phát biểu trước báo chí ở Hà Nội"

Trong câu này có nhiều tín hiệu:

| Thành phần | Loại search phù hợp    |
| ---------- | ---------------------- |
| Thủ tướng  | Entity Search          |
| Hà Nội     | Entity/Metadata Filter |
| phát biểu  | Semantic Search        |
| báo chí    | Semantic + Object      |
| cảnh       | Timeline               |

Nếu chỉ dùng Vector Search thì chưa đủ.

Nếu chỉ dùng Keyword Search cũng chưa đủ.

Hybrid Search là kết hợp tất cả.

---

# Kiến trúc

```text
                  Natural Language Query
                           │
            ┌──────────────┴──────────────┐
            │                             │
      Query Understanding            Query Embedding
            │                             │
      Extract Filters              Embedding Model
            │                             │
            │                     Vector Search
            │                             │
     Metadata Search               Top 100 scenes
            │                             │
      BM25 Full Text               Similarity Score
            └──────────────┬──────────────┘
                           │
                    Candidate Merge
                           │
                      Re-ranking
                           │
                    Top 10 Results
                           │
                  Scene + Timestamp
```

---

# Bước 1: Query Understanding

LLM hoặc parser sẽ phân tích câu hỏi.

Ví dụ:

```text
"Tìm cảnh Messi ghi bàn trong hiệp hai"
```

Chuyển thành

```json
{
  "semantic": "Messi ghi bàn",
  "filters": {
    "player": "Messi",
    "half": 2
  }
}
```

Ví dụ khác

```text
"Cảnh có xe cứu hỏa ban đêm"
```

↓

```json
{
    "objects":["Fire Truck"],
    "time":"Night"
}
```

Không phải mọi thứ đều đưa vào embedding.

---

# Bước 2: Metadata Filter

Lọc trước.

Ví dụ

SQL

```sql
WHERE
Channel='VTV1'

AND

BroadcastDate>'2026-01-01'
```

Hoặc

```sql
Person='Messi'
```

Giảm từ

```text
10 triệu scene

↓

5000 scene
```

---

# Bước 3: BM25 Search

Search trên

* Transcript
* OCR
* Summary

Ví dụ

```text
"World Cup"
```

BM25 rất mạnh.

Nó sẽ tìm

```
World Cup
```

chính xác.

---

# Bước 4: Vector Search

Sinh embedding.

Ví dụ

Query

```
"Cảnh người dẫn chương trình đứng trước bản đồ thời tiết"
```

↓

Embedding

↓

Qdrant

↓

Top 100 Scene

Không cần từ "bản đồ thời tiết" xuất hiện trong transcript.

---

# Bước 5: Merge

Giả sử

BM25

```
Scene 5

Score 0.91
```

Vector

```
Scene 5

Score 0.81
```

Metadata

```
Scene 5

Score 1.0
```

Ghép

```
Scene 5

Final

0.94
```

---

# Bước 6: Re-ranking

Đây là bước quan trọng nhất.

Ví dụ

Top 20 Scene.

LLM hoặc reranker sẽ đọc

```
Summary

Transcript

Objects

OCR

Faces
```

rồi đánh giá

```
Query

↓

Scene

↓

Relevant

9.8
```

Ví dụ

```
Query

"Tìm cảnh người đàn ông mặc áo đỏ đang cầm micro"
```

Scene A

```
Summary

Người đàn ông mặc áo đỏ đang trả lời phỏng vấn.
```

↓

Score

9.8

Scene B

```
Summary

Người dẫn chương trình mặc áo xanh.
```

↓

Score

3.1

---

# API hoạt động như thế nào

Giả sử frontend gọi

```http
POST /api/search
```

Body

```json
{
    "query":"Tìm cảnh xe cứu hỏa chạy qua cầu"
}
```

API sẽ thực hiện

```text
Search API

↓

Embedding

↓

Vector Search

↓

BM25

↓

Metadata

↓

Merge

↓

Rerank

↓

Return
```

Response

```json
{
  "results": [
    {
      "scene_id": "scene_123",
      "video_id": "video_01",
      "start": 185.2,
      "end": 194.6,
      "score": 0.97,
      "summary": "Xe cứu hỏa chạy qua cầu trong đêm.",
      "thumbnail": "...",
      "highlights": [
        "fire truck",
        "bridge"
      ]
    }
  ]
}
```

---

# Mình khuyên chia thành các service

```text
                Search API
                     │
      ┌──────────────┼──────────────┐
      │              │              │
Query Parser   Embedding      Metadata Filter
      │              │              │
      └──────┬───────┴──────────────┘
             │
       Candidate Generator
             │
      ┌──────┴──────┐
      │             │
 Vector Search   BM25 Search
      │             │
      └──────┬──────┘
             │
      Candidate Merge
             │
         Reranker
             │
      Search Result API
```

Kiến trúc này giúp bạn dễ thay thế từng thành phần mà không ảnh hưởng toàn hệ thống.

## Với stack của bạn

Với pipeline:

* PySceneDetect
* Faster Whisper
* InsightFace
* YOLOE
* SigLIP2
* EasyOCR/VietOCR
* Qwen

mình sẽ thiết kế **Hybrid Search** theo hướng này:

| Thành phần        | Công nghệ                                                       | Vai trò                                                           |
| ----------------- | --------------------------------------------------------------- | ----------------------------------------------------------------- |
| Structured filter | PostgreSQL                                                      | Lọc theo kênh, ngày phát sóng, người, chương trình, thời lượng... |
| Full-text search  | PostgreSQL FTS hoặc OpenSearch                                  | Tìm chính xác trên transcript, OCR, summary, keywords             |
| Vector search     | pgvector hoặc Qdrant                                            | Tìm kiếm ngữ nghĩa trên `scene_embedding`                         |
| Candidate merger  | Search API                                                      | Hợp nhất và loại bỏ trùng lặp các scene                           |
| Reranker          | Qwen hoặc một mô hình reranker chuyên dụng như **BGE Reranker** | Xếp hạng lại theo ngữ cảnh truy vấn                               |
| Result formatter  | Search API                                                      | Trả về timestamp, thumbnail, score, highlights và lý do khớp      |

### Ví dụ luồng xử lý

Truy vấn:

> "Tìm cảnh MC đứng trước màn hình thời tiết và nhắc đến bão số 3"

1. **Metadata filter**: nếu có điều kiện về chương trình hoặc thời gian thì lọc trước.
2. **Full-text**: tìm `"bão số 3"` trong transcript và OCR.
3. **Vector search**: tìm các scene có ngữ nghĩa gần với "MC đứng trước màn hình thời tiết".
4. **Merge**: gộp danh sách ứng viên từ cả hai nguồn.
5. **Rerank**: ưu tiên scene vừa có transcript nói về bão số 3, vừa có object/person/summary phù hợp.
6. **Trả kết quả**: scene, thời gian bắt đầu/kết thúc, thumbnail và điểm liên quan.

Điểm mấu chốt là **Hybrid Search không phải là một thuật toán**, mà là một **pipeline** kết hợp nhiều phương pháp truy hồi. Điều này vừa tận dụng được độ chính xác của full-text search, vừa có khả năng hiểu ngữ nghĩa của vector search, đồng thời vẫn khai thác được metadata có cấu trúc để lọc và xếp hạng kết quả hiệu quả.

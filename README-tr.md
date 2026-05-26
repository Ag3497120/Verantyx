<div align = "merkez">
  <h1>🛡️ Verantyx IDE ve Cortex Motoru</h1>
  <p><b>Sıfır Sızıntılı, Nöro-Sembolik Yapay Zeka Kodlama Ağ Geçidi ve Yerel macOS IDE</b></p>

<p>
    <a href = "https://github.com/verantyx/verantyx/releases/latest"><img src = "https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt = "Sürüm 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">İngilizce</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Basitleştirilmiş Çince</a> · <a href="README-zh-TW.md">Geleneksel Çince</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">Japonca</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

## 📖 Verantyx Hakkında

Bu proje için, daha önce kural tabanlı bir sembolik yapay zeka oluşturmaya çalışırken, bunu kendi başıma yaratmanın imkansız olacağını fark ettim ve şu anda yaygın olan yapay zekanın koşum takımı gibi benim tarafımdan kontrol edilen parçaları oluşturarak onu kontrol etmeye karar verdim. (O zamanlar açık pençe dikkat çekiyordu)
Oradan bu projeyi geliştirmeye başladım çünkü kaynak kodunu ve kullanıcı isteklerini buluttaki yüksek performanslı yapay zekaya aktarmadan önce bulmaca benzeri bir durumda gizleyerek bilgi sızıntılarını önlemenin mümkün olabileceğini düşündüm.

Bu projenin 0 yıldıza sahip olmasının nedeni, güvenli bir klasör içermesi ve onu aniden özel bir depo haline getirmem ve böylece 9 yıldızın ortadan kaybolmasıdır. Tamamen iyileştiğim için sürekli desteğiniz için teşekkür ederim. Diğer depolarla örtüşen kısımları ayırdım. Esas olarak bu depodaki sürümleri yayınlıyordum, ancak kaynak kodu güncellemesinin geciktiğini fark ettim ve güncelledim.

Bundan sonra ana dilim olan Japoncaya yoğunlaşmayı ve İngilizceyi normal bir çeviri aracı kullanarak çevirip her ihtimale karşı yayınlamayı düşünüyorum.

## 🔐 Gizleme ve 6 eksenli 3D çapraz yapı

Bu projeyi gizlemenin ardındaki fikir, ilk zamanlarda verilerin nasıl iletileceğinin bir görüntüsü olarak oluşturulan verantyx'in öncülü olan Axis'te bulunan üç boyutlu çapraz yapıya dayalı bir veri yönetimi yöntemi kullanmaktır.

### 🧩 6 boyutun tanımı (Eksen)

| Eksen | İsim | Rol / Çıkarılan öğeler |
| :--- | :--- | :--- |
| **X ekseni** | **Kontrol Akışı** | Zaman ve düzen ekseni. 'if' dalları, 'for' döngüleri, istisna yönetimi vb. |
| **Y ekseni** | **Veri Akışı** | Bağımlılık ekseni. Değişken atama, bağımsız değişken aktarma vb. |
| **Z ekseni** | **Tür Kısıtlamaları** | Sınır ekseni. Sınıf tanımları, tür açıklamaları, jenerikler vb. |
| **W ekseni** | **Bellek Yaşam Döngüsü** | Yaşam ekseni. Kapsam ömrü, bellek ayırma/bırakma. |
| **V ekseni** | **Kapsam Hiyerarşisi** | Dahil etme ekseni. Modül, sınıf içi içe geçme yapısı. |
| **U ekseni** | **Anlambilim ve Anlam** | **★En önemlisi★ İş niyeti ekseni. Somut değişken adları, işlev adları, ham dizeler ve sayılar. ** |

Dönüştürme işlemi Verantyx'in **Gatekeeper Engine** tarafından MacBook'unuzda anında yerel olarak gerçekleştirilir.

---

### 🔄 Opak Topoloji dönüşüm mekanizmasına ham kod

#### 1. Adım: AST'ye (Soyut Sözdizimi Ağacı) ayrıştırma ve ayrıştırma
İlk olarak, Gatekeeper motoru (kural tabanlı önerilir) hedef kaynak kodunu ayrıştırır ve program yapısını AST (Soyut Sözdizimi Ağacı) adı verilen ağaç yapılı verilere dönüştürür.
Bu noktada ``hangi fonksiyon neyi çağırıyor?'', ``değişken isimleri nelerdir ve string olarak tanımlanan nedir?'' gibi tüm bilgiler hala yer almaktadır.

#### Adım 2: Anlambilimin "fiziksel ayrımı ve izolasyonu" (U ekseni)
Verantyx'in parladığı yer burası. AST'den **işin anlamını (niyetini) belirten tüm bilgileri = U ekseni** fiziksel olarak çıkarın.

* **Sökülen şeyler (U ekseni)**: Değişken adları, işlev adları, dizeler, sabit sayılar vb.
* **Geriye kalan (X, Y, Z, W, V eksenleri)**: ``Bir değişken atamak'', ``fonksiyon çağırmak'', ``if ifadesi ile dallanma'' ve ``for ifadesi ile döngü yapmak'' mantıksal çerçevesi.

Çıkarılan belirli ad ve dize verileri, Mac'inizin **`JCrossIRVault` (kasa)** içinde yerel olarak güvenli bir şekilde depolanır ve asla dışarıya gönderilmez.

#### Adım 3: Opak Düğüme tamamen şifrelenmiş
Anlamdan arındırılmış kalan "kemikler", bulut LLM'ye gönderilmek üzere tamamen opak bir temsile dönüştürülür.

* **`NODE[0x...]' (Düğüm Kimliği)**: Tüm değişkenler ve sözdizimi öğeleri, rastgele bellek adresleri gibi tanımlayıcılarla değiştirilir.
* **`ARITY` (arity/terim sayısı)**:
    * `class.nullary`: Bağımsız değişkeni veya içeriği olmayan bir öğe (yalnızca bir değer veya terminal düğümü).
    * `sınıf.standart`: Standart tekli ve ikili işlemler (A + B, atama vb.).
    * `class.multiway`: Birden fazla öğeye sahip karmaşık yapılar (döngüler, if-else dalları, işlev tanımları vb. için).
* **`HASH` (Yapısal Hash)**: Düğümün grafikte nerede olduğunu ve çevresine nasıl bağlandığını gösteren bir sağlama toplamı. Bu, LLM bulmacayı çözüp geri getirdiğinde yapının bozulmadığını yerel olarak doğrulamanıza olanak tanır.

Orijinal kod ifadesi bile kaybolur ve saf bir matematiksel grafik haline gelir: `class.multiway` düğümleri, alt düğümleri üzerinde yinelenir.''

#### Adım 4: İstatistiksel çıkarımı önlemek için "tuzakları" enjekte etme
Kodunuzu bir grafik yapısında harici bir tarafa gönderirseniz, gelişmiş yapay zeka veya kötü niyetli saldırganların istatistiksel olarak bu grafiğin şeklinin ortak bir komut dosyasının şekli olduğu sonucunu çıkarması (tersine mühendislik) riski vardır.

Bunu önlemek için grafikteki boşluklara rastgele **sahte düğümler (tuzak)** enjekte ediyoruz.
```metin
// _TOKEN_匶:0.2___jcross_BM_505__ [yaratıcı meta veriler]
'''''
Bu anlamsız Kanji belirteçleri ve sahte bağlantıların karıştırılmasıyla grafiğin şekli bozulur ve harici yapay zekanın orijinal kaynak kodunun gerçek kimliğini çıkarması matematiksel olarak imkansız hale gelir.

---

### 🧩 Yüksek Lisans bunu nasıl “düzeltir”? (Restorasyon süreci)

1. **Bulmaca olarak çözün**:
   LLM, orijinal kodu bilmeden, hedef değişikliğin değerini belirtilen bağlamdan ve grafiğin şeklinden (ARITY ve HASH bağlantıları) çıkarır.
2. **Yapısal yamayı iade etme**:
   LLM yalnızca içeriği yeniden yazan JSON formatındaki yapısal yamaları (GraphPatch) döndürür.
3. **Yerel Ters Transpilasyon**:
   Mac'in Gatekeeper motoru yamayı alır ve daha önce "JCrossIRVault"ta gizlenen gerçek değişken adını ve dizeyi (U ekseni) yamaya yeniden enjekte eder.

Sonuç olarak, hiçbir bilgi sızıntısı olmayan sihirli bir geliştirme deneyimi elde ediliyor; ``Harici yapay zeka, orijinal kodun tek bir satırını bile görmemiş veya anlamamış olsa da, yerel koda döndüğünde kod doğru bir şekilde yeniden yazılmıştır.''** *Gözden kaçırdığım bilgi sızıntıları olabilir, eğer fark ederseniz lütfen sorun yoluyla bize bildirin.

---

## ⚠️ Şu anda halledemediğim görevler (iyi değilim)

Şu anda bu yapı, genellikle en zayıf görev olan **Swift'ten Rust'a yeniden yazma** gibi görevleri yerine getirememektedir. Ayrıca aşağıdaki 1'den 4'e kadar olan görevler benim için zor.

### 1. "Anlambilime (alan bilgisi)" bağlı yeniden düzenleme ve hata düzeltmeleri
Harici LLM yalnızca `NODE[0x...]' iskeletini gördüğü için ``kodun anlamını anlamadan çözülemeyen sorunlarla'' baş edemez.
* **❌ Zayıf talimat örneği**: "Kimlik doğrulamayla ilgili tüm değişkenlerin adlarına `auth_` önekini ekleyin."
* **Sebep**: LLM'nin "hangi kimlik doğrulama süreci" konusunda görünürlüğü yoktur.

### 2. Büyük ölçüde harici kütüphanelere (API) bağlı olan yeni işlevlerin eklenmesi
Kaynak kodundaki tüm "import" ifadeleri ve kütüphane çağrıları da "NODE" olarak şifrelenir, bu da belirli kütüphaneler hakkında bilgi gerektiren görevleri zorlaştırır.
* **❌ Zayıf talimat örneği**: "AWS S3'e dosya yükleme özelliğini ekleyin."
* **Sebep**: LLM, mevcut kodun hangi harici kütüphaneleri kullandığını bilmiyor.

### 3. "Sıfırdan tamamen yeni bir özellik" yazmak
Gatekeeper, ``mevcut yapıları yamalama ve değiştirme (AST)'' konusunda son derece güçlüdür ancak ``boş bir sayfadan hem anlam (U ekseni) hem de yapıya sahip devasa yeni özellikler yaratma'' konusunda zayıftır.

### 4. Yüksek Lisans'ın "ön öğrenme bilgisinin" etkisizliği nedeniyle çıkarımın bozulması
Gemma ve Claude gibi Yüksek Lisans'lar dünyanın her yerindeki kaynak kodlarını inceleyerek daha akıllı hale geldiler, ancak Verantyx'in gönderdiği format ``dünyadaki diğer dillerden farklı olarak saf sembollerden ve karmalardan oluşan bir grafiktir.''
* **Sebep**: LLM'nin uzmanlığı olan ``kod bağlamından örüntü tanıma'' engellendiğinden, daha önce hiç görmediğiniz zor bir matematiksel grafik bulmacası haline gelir ve hesaplama maliyetlerinin artmasına neden olur.

### 💡Bunu nasıl aşıyorsunuz? (Geleceğe bakış)
Şu anda Verantyx, bu zayıflıkların üstesinden gelmek için "Üç Katmanlı JCross Bellek" ve **Görsel Bağlantıların bir kombinasyonunu uyguluyor. Yalnızca hassas bilgiler içermeyen güvenli meta verilerin kısmen LLM'ye görsel çapa olarak sunulduğu, güvenliği korurken ipuçları veren bir yaklaşım benimsiyoruz.

---

## 📽️ Demo video ve kod dönüşümü iş başında

<p align = "orta">
  <img src = "demo.gif" alt = "Verantyx Gatekeeper Demosu" width = "49%" style = "border-radius: 8px;">
  <video src = "https://github.com/verantyx/verantyx/releases/download/v1.2.5/demo_skill_jenerasyon.mov" controls = "controls" muted = "muted" width = "49%" style = "border-radius: 8px;"></video>
</p>

### Öncesi ve Sonrası: Şaşırtma iş başında

**[Önce] Ham Kaynak Kodu (Yerel Ortam)**
```piton
json'u içe aktar
işletim sistemini içe aktar
ithalatı kapat
içe aktarma istekleri
içe aktarma alt işlemi
yeniden içe aktar
tqdm'den tqdm'yi içe aktar
sistemi içe aktar

# Yeni ayrıştırıcımızı içe aktar
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
verantyx.cross_engine.jcross_extraction_parser'dan JCrossExtractionParser'ı içe aktarın

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json"
TARGET_DIR = "/Kullanıcılar/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7"
QUERY_BIN = "/Kullanıcılar/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross"
MODEL = "gemma4:e2b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FINAL_REPORT = "/Kullanıcılar/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_1_accuracy_report.json"
'''''

**[Sonra] Gatekeeper JCross Opak Topolojisi (Cloud LLM'ye Gönderildi)**
"peltek"
;;; 🛡️ GATEKEEPER MODU — JCross IR Görünümü
;;; Gerçek tanımlayıcıların yerini düğüm kimlikleri almıştır.
;;; Şema: D59144D1-BE1
;;; Düğümler: 124 | Düzenlenen sırlar: 3442
;;; Kaynak: cortex/bench_v7_1_puzzle_runner.py
;;;
// JCROSS_6AXIS_BEGIN
// dil:hızlı belge:0xD5E025

// ── ÜST DÜZEY DÜĞÜMLER
  NODE[0x7995] tür:opak TÜR:opak MEM:opak HASH:0xb4af0a52 ARITY:class.multiway
  NODE[0x9DB8] tür:opak TÜR:opak MEM:opak HASH:0x504933fd ARITY:class.standard
  NODE[0x627F] tür:opak TÜR:opak MEM:opak HASH:0x97b540cb ARITY:class.multiway
  NODE[0x7F4C] tür:opak TÜR:opak MEM:opak HASH:0x86742e8c ARITY:class.standard
  NODE[0xC79E] tür:opak TÜR:opak MEM:opak HASH:0xd42206c4 ARITY:class.standard
  NODE[0x510B] tür:opak TÜR:opak MEM:opak HASH:0x14b9be4e ARITY:class.nullary
  NODE[0xB5C0] tür:opak TÜR:opak MEM:opak HASH:0xcacb18a2 ARITY:class.standard
// _TOKEN_匶:0.2___jcross_BM_505__ [yaratıcı meta veriler]
  NODE[0xE3CF] tür:opak TÜR:opak MEM:opak HASH:0x375a5480
'''''

---

## 💻 Kurulum yöntemi (kaynaktan derleme)

**Gereksinimler:**
- macOS 14.0 veya üzeri (Apple Silicon şiddetle tavsiye edilir)
- Xcode 15.0 veya üzeri

``` bash
git klonu https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
Verantyx.xcodeproj'u açın
# Verantyx şemasını seçin ve oluşturmak ve çalıştırmak için Cmd+R tuşlarına basın
'''''

*Not: Windows/Linux bağlantı noktaları (Rust core + llama.cpp) uzun vadeli yol haritasında yer alıyor ancak şu anda yerel macOS/MLX mimarisini tamamlamaya son derece odaklanmış durumdayız. *

---

## 🔧 Depo ayarları ve geçmişi hakkında

**Git ayarlarıyla ilgili bildirim:**
Bu depoya ilk kayıtlar, geliştiricinin macOS kullanıcı adından türetilen yerel Git adı `kofdai` altında yapıldı. Bu sorun 24 Mayıs 2026 itibarıyla düzeltildi ve artık tüm kayıtlar doğru şekilde "@Ag3497120" ile ilişkilendiriliyor. Bu, geliştirme ortamınızı ayarlarken sık karşılaşılan bir sorundur ve bir bot veya otomatik araçtan kaynaklanmaz. Gelecekteki tüm katkılar doğru yazar adıyla kaydedilecektir.

---

## 💡 Soru-Cevap ve İtiraz (Deneysel Özellikler)

Şu anda **Verantyx Agent**'ı "Kontrol" tuşuna üç kez basarak başlatabilirsiniz.

<p align = "orta">
  <img src = "assets/verantyx_agent_v2.png" alt = "Verantyx Agent Arayüzü" width = "600" style = "border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
</p>

Bu mod, önceki uygulamalarda bulunan çeşitli IDE modları için bir test alanı olarak oluşturulmuştur. Projenin tamamını gözden geçirmek ve gerçekten ihtiyaç duyulan "geçit denetleyicisi moduna" odaklanmak için, şu ana kadar oluşturduğumuz temsilci davranışına yönelik deneysel özellikleri **Verantyx Agent**'ta birleştirdik.

Önceki sürümlerde yer alan ana aracı özellikleri şunlardır:

* **Dual Twin denetim sistemi**: Yapay zekanın araçları çağırması ve ihmalkar olması sorununu önlemek için TwinB'nin, JCross'u dahili olarak enjekte ederek TwinA'nın araç çağrılarının geçerliliğini denetlediği bir mekanizma başlattık.
* **Görsel Sabitlemenin Tanıtımı**: Becerileri ve talimatları yalnızca yönlendirmelerle kontrol etmekten, Görsel Bağlantıyı kullanarak görüntü enjeksiyonu ve yönlendirmelerin hibrit yöntemine geçiş yaptık.
* **L3.5 İşletim Sistemi Varlık Haritasının Oluşturulması**: Control×3 ile başlatılan aracıda, "L3.5" adı verilen dahili bilgisayar haritası yalnızca yerel olarak korunur. Temsilcilere, bilgisayarlarındaki varlıkların kendi istihbaratlarıyla bağlantılı olduğu bilincini aşıladık.
* **AX API kullanarak yüksek hassasiyetli GUI işlemi**: Ekran kaydetmeyi kullanan mevcut GUI işleminden, OS API ağacını (erişilebilirlik API'si) kullanan güvenilir ve yüksek hassasiyetli işleme geçtik.
* **Kanji topolojisi sıkıştırması**: Bir L3.5 haritasını bir bağlama enjekte ederken, bir görüntü oluşturun ve bağlamın şişmesini önlemek için bunu bir bilgi istemi olarak kullanın. "Kanji Topolojisi" adı verilen benzersiz bir sıkıştırma formatını gerçek verilerle ilişkilendirerek, yalnızca gerekli verilerin uygun şekilde enjekte edilmesini sağladık.
* **Ajan modu genişletmesi**: İki tür eklendi: "Otomatik mod" ve "Gelişmiş mod".
* **Dahili bilgi önceliği modu**: Kısıtlama-kaldırma modellerini kullanan uzman kullanıcılar için, yerel yapay zekayı yalnızca bir orkestratör olarak değil aynı zamanda ana düşünme modeli ve bilgi kaynağı olarak da tam olarak kullanmalarına olanak tanıyan bir mod uyguladık.
* **L3.5 ayrılmış hafıza hattı**: L3.5 harita hafızasının karmaşık ve büyük olmasını önlemek için normal konuşma hafızasından tamamen ayrı bir hafıza hattı oluşturduk.
* **İnce ayar uygulaması**: L1'den L3.5'e kadar olan belleklerden kullanıcı kimlik verilerini çıkarmak ve herhangi bir model üzerinde ince ayar yapmak (tek başına bellek sistemiyle mümkün olmayan optimizasyonu elde etmek) için dayanak noktası olarak kullanılabilecek bir işlevi hayata geçirdik.
* **FAR bölge yapısının benimsenmesi**: ``Anıları silmeden düzenleme'' felsefesinden yola çıkarak, bir görev tamamlandığında görev paketi ve başlık gibi geçiş sürecini kaydeden ve bunu ``FAR bölgesi'' adı verilen yeni bir katmana bırakan bir yapıyı benimsedik. Bu, iş süreçleri gibi önemli anıların görev tamamlandıktan sonra bile korunmasını sağlar.

Bunlar şu anda eklenen özelliklerden sadece birkaçı.
Yakın zamanda yapılan bir güncelleme, HuggingFace'te yayınlanan 'talkie-1930:13b'nin kısmen nicelenmiş bir versiyonunu kullanan orkestrasyonu (Blind Commander Architecture) tanıttı. “Yalnızca 1930'dan kalma bilgiye sahip olma” sınırlamasından yararlanarak, komutları yürütmek için kural tabanlı bir aracı kullanıyoruz ve kullanıcının mesajını zamanın mecazi ifadelerine dönüştürme rolüne sahibiz. Projenin "deneysel" felsefesini somutlaştıran ek özellikler ekleniyor.

### 🔄 Gelecekteki yol haritası ve büyük zorluklar

Bu aracı ve ağ geçidi denetleyicisi modu şu anda aynı depolama alanına bağlı ancak gelecekte bunların ayrılmasını ve ince ayar yapılmasını sağlayacak bir işlevi uygulamayı planlıyoruz.

Şu anda, bu ajan geliştirme geçici bir dönüm noktasına ulaştı. Ben de bir öğrenci olduğum için, bu temsilci Teams vb.'de verilen görevleri tam olarak yerine getirebildiğinde ("En son ödevleri oluşturma ve gönderme" gibi görevler), şu anda bir iyileştirme planı olarak üzerinde çalıştığım "Gatekeeper Modu"nun tam ölçekli geliştirilmesine başlamak istiyorum. Yıldız veren herkese teşekkür ederiz. Lütfen bir süre bekleyin.

Son olarak bu projenin sonucu olarak hazırladığımız ekstra büyük mücadeleden bahsetmek istiyorum.

1. **Windows sürümüne taşıma (Rust tabanlı)**: Bu görev, şu anda macOS için Swift dilinde yazılan uygulamayı Rust tabanlı olarak yeniden yazmaktır, böylece Windows kullanıcıları da aynı ağ geçidi denetleyicisi işlevini deneyimleyebilir.
2. **Buluta bağımlılıktan tamamen kurtulmak**: Pahalı API ücretleri ödemeden yalnızca yerel LLM'yi kullanarak bağımsız olarak geliştirmeye devam edebilen bir aracıya dönüşmek. MacBook üzerinde çalışan 20B sınıfı bir model kullanmak (belirli koşullar altında en üst düzey modelle kıyaslanabilir olduğu söylenen güncel 'qwen3.6:27b' gibi), bulut seviyesine yakın bir kodlama aracısı çalıştırmak ve otonom olarak iyileştirmeler yaparak projeye devam etmek istiyoruz.
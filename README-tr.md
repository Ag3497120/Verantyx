<div align = "merkez">
  <h1>🛡️ Verantyx (Doğrulanabilir ve Denetlenebilir Yapay Zeka Motoru)</h1>
  <p><b>Sıfır Sızıntılı, Nöro-Sembolik Yapay Zeka Kodlama Ağ Geçidi ve Yerel macOS IDE</b></p>

<p>
    <a href = "https://github.com/verantyx/verantyx/releases/latest"><img src = "https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt = "Sürüm 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README.md">İngilizce</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Basitleştirilmiş Çince</a> · <a href="README-zh-TW.md">Geleneksel Çince</a> · <a href="README-ko.md">한국어</a> · <a href="README-ja.md">Japonca</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

Verantyx, yapay zeka destekli yazılım geliştirmeyi tamamen kontrol edilebilir ve güvenli hale getiren yeni nesil bir Nöro-Sembolik mantık motorudur.
Güçlü bir çekirdek motorun (JCross/L3.5 Bellek) üzerinde iki farklı ön uç sunuyoruz. Lütfen amacınıza göre seçiniz.

---

## 1. 🖥️ Verantyx Gatekeeper (IDE Modu)
**"Bulut Yüksek Lisans Programının şirketimin gizli kodunu güvenli bir şekilde okumasını istiyorum"**

Gatekeeper modu, kaynak kodunuzu yapay zekaya aktarmadan önce anlamsız matematiksel bulmacalara (Opak Topoloji) dönüştüren son derece güvenli IDE'dir.
👉 [Gatekeeper modu ve gizleme mekanizmasının ayrıntıları için buraya tıklayın (README-Gatekeeper.md)](./docs/README-Gatekeeper.md)

## 2. ⚡ Verantyx Agent (Spot Işığı Modu)
**"Beynimin bir uzantısı olarak en güçlü yerel yapay zekayı tam anlamıyla kullanmak istiyorum"**

Sadece 'Kontrol' tuşuna üç kez basılarak etkinleştirilebilen hiper-otonom bir ajandır. Dual Twin'i kullanan iç denetim, 1930 metaforunu kullanan halüsinasyonların fiziksel olarak engellenmesi ve bilgisayar varlıklarını "kendi anılarınız (L3.5)" olarak tanıyan yeni nesil bir düşünme motoruyla donatılmıştır.
👉 [Ajan modunun ayrıntıları ve mimarisi için buraya tıklayın (README-Agent.md)](./docs/README-Agent.md)

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

## 📖 Verantyx Hakkında

Bu proje için, daha önce kural tabanlı bir sembolik yapay zeka oluşturmaya çalışırken, bunu kendi başıma yaratmanın imkansız olacağını fark ettim ve şu anda yaygın olan yapay zekanın koşum takımı gibi benim tarafımdan kontrol edilen parçaları oluşturarak onu kontrol etmeye karar verdim. (O zamanlar açık pençe dikkat çekiyordu)
Oradan bu projeyi geliştirmeye başladım çünkü kaynak kodunu ve kullanıcı isteklerini buluttaki yüksek performanslı yapay zekaya aktarmadan önce bulmaca benzeri bir durumda gizleyerek bilgi sızıntılarını önlemenin mümkün olabileceğini düşündüm.

Bu projenin 0 yıldıza sahip olmasının nedeni, güvenli bir klasör içermesi ve onu aniden özel bir depo haline getirmem ve böylece 9 yıldızın ortadan kaybolmasıdır. Tamamen iyileştiğim için sürekli desteğiniz için teşekkür ederim. Diğer depolarla örtüşen kısımları ayırdım. Esas olarak bu depodaki sürümleri yayınlıyordum, ancak kaynak kodu güncellemesinin geciktiğini fark ettim ve güncelledim.

Bundan sonra ana dilim olan Japoncaya yoğunlaşmayı ve İngilizceyi normal bir çeviri aracı kullanarak çevirip her ihtimale karşı yayınlamayı düşünüyorum.

---

## 🔧 Depo ayarları ve geçmişi hakkında

**Git ayarlarıyla ilgili bildirim:**
Bu depoya ilk kayıtlar, geliştiricinin macOS kullanıcı adından türetilen yerel Git adı `kofdai` altında yapıldı. Bu sorun 24 Mayıs 2026 itibarıyla düzeltildi ve artık tüm kayıtlar doğru şekilde "@Ag3497120" ile ilişkilendiriliyor. Bu, geliştirme ortamınızı ayarlarken sık karşılaşılan bir sorundur ve bir bot veya otomatik araçtan kaynaklanmaz. Gelecekteki tüm katkılar doğru yazar adıyla kaydedilecektir.
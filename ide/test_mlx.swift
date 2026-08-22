import Foundation
import MLXLMCommon
import CoreImage

let img = CIImage(color: .black)
let _ = UserInput(prompt: "Test", images: [UserInput.Image.ciImage(img)])

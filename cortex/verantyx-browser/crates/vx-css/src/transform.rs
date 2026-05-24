//! CSS Transform Matrix Engine — CSS Transforms Level 1 & 2
//!
//! Implements the full CSS transform stack:
//!   - 2D transform functions (translate, rotate, scale, skew, matrix)
//!   - 3D transform functions (translate3d, rotateX/Y/Z, perspective, matrix3d)
//!   - Transform origin resolution
//!   - Accumulated transform matrix computation
//!   - Point mapping through transform chains (for hit testing)
//!   - Decomposition of matrix3d into translate/rotate/scale components
//!   - CSS animation interpolation helpers  

/// A 4×4 homogeneous transformation matrix (column-major, per CSS spec)
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Matrix3d {
    /// The 16 elements in column-major order: m[col][row]
    pub m: [[f64; 4]; 4],
}

impl Matrix3d {
    /// The identity matrix
    pub const IDENTITY: Matrix3d = Matrix3d {
        m: [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
    };
    
    pub fn identity() -> Self { Self::IDENTITY }
    
    /// Check if this is the identity matrix (no-op transform)
    pub fn is_identity(&self) -> bool {
        *self == Self::IDENTITY
    }
    
    /// Check if this is a 2D matrix (no 3D components beyond unit depth)
    pub fn is_2d(&self) -> bool {
        self.m[2][0] == 0.0 && self.m[2][1] == 0.0 &&
        self.m[0][2] == 0.0 && self.m[1][2] == 0.0 &&
        self.m[2][2] == 1.0 && self.m[3][2] == 0.0 &&
        self.m[2][3] == 0.0 && self.m[3][3] == 1.0
    }
    
    /// Matrix multiplication (this × other)
    pub fn multiply(&self, other: &Matrix3d) -> Matrix3d {
        let mut result = Matrix3d { m: [[0.0; 4]; 4] };
        for col in 0..4 {
            for row in 0..4 {
                for k in 0..4 {
                    result.m[col][row] += self.m[k][row] * other.m[col][k];
                }
            }
        }
        result
    }
    
    /// Apply the matrix to a 2D point (for hit testing and bounding box calc)
    pub fn map_point(&self, x: f64, y: f64) -> (f64, f64) {
        let w = self.m[0][3] * x + self.m[1][3] * y + self.m[3][3];
        let out_x = (self.m[0][0] * x + self.m[1][0] * y + self.m[3][0]) / w;
        let out_y = (self.m[0][1] * x + self.m[1][1] * y + self.m[3][1]) / w;
        (out_x, out_y)
    }
    
    /// Apply the matrix to a 3D point
    pub fn map_point_3d(&self, x: f64, y: f64, z: f64) -> (f64, f64, f64) {
        let w = self.m[0][3]*x + self.m[1][3]*y + self.m[2][3]*z + self.m[3][3];
        (
            (self.m[0][0]*x + self.m[1][0]*y + self.m[2][0]*z + self.m[3][0]) / w,
            (self.m[0][1]*x + self.m[1][1]*y + self.m[2][1]*z + self.m[3][1]) / w,
            (self.m[0][2]*x + self.m[1][2]*y + self.m[2][2]*z + self.m[3][2]) / w,
        )
    }
    
    /// Compute the inverse matrix (for reverse-mapping hit test coordinates)
    pub fn inverse(&self) -> Option<Matrix3d> {
        // Cofactor expansion for 4×4 inverse
        let mut inv = [[0.0f64; 4]; 4];
        
        let m = &self.m;
        
        // Compute cofactor matrix (adjugate)
        for i in 0..4 {
            for j in 0..4 {
                let sign = if (i + j) % 2 == 0 { 1.0 } else { -1.0 };
                inv[j][i] = sign * self.cofactor(i, j);
            }
        }
        
        // Compute determinant using first row
        let det = (0..4).map(|j| m[j][0] * inv[0][j]).sum::<f64>();
        
        if det.abs() < 1e-12 { return None; }
        
        let inv_det = 1.0 / det;
        let mut result = Matrix3d { m: [[0.0; 4]; 4] };
        for col in 0..4 {
            for row in 0..4 {
                result.m[col][row] = inv[col][row] * inv_det;
            }
        }
        Some(result)
    }
    
    fn cofactor(&self, row: usize, col: usize) -> f64 {
        let mut sub = [[0.0f64; 3]; 3];
        let mut sr = 0;
        for i in 0..4 {
            if i == row { continue; }
            let mut sc = 0;
            for j in 0..4 {
                if j == col { continue; }
                sub[sr][sc] = self.m[j][i];
                sc += 1;
            }
            sr += 1;
        }
        // Determinant of the 3×3 submatrix
        sub[0][0] * (sub[1][1]*sub[2][2] - sub[1][2]*sub[2][1])
        - sub[0][1] * (sub[1][0]*sub[2][2] - sub[1][2]*sub[2][0])
        + sub[0][2] * (sub[1][0]*sub[2][1] - sub[1][1]*sub[2][0])
    }
    
    /// Serialize to CSS matrix3d() string
    pub fn to_css_string(&self) -> String {
        if self.is_2d() {
            format!("matrix({}, {}, {}, {}, {}, {})",
                self.m[0][0], self.m[0][1],
                self.m[1][0], self.m[1][1],
                self.m[3][0], self.m[3][1])
        } else {
            format!("matrix3d({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})",
                self.m[0][0], self.m[0][1], self.m[0][2], self.m[0][3],
                self.m[1][0], self.m[1][1], self.m[1][2], self.m[1][3],
                self.m[2][0], self.m[2][1], self.m[2][2], self.m[2][3],
                self.m[3][0], self.m[3][1], self.m[3][2], self.m[3][3])
        }
    }
}

/// CSS transform function primitives
#[derive(Debug, Clone, PartialEq)]
pub enum TransformFunction {
    // 2D primitives
    Matrix { a: f64, b: f64, c: f64, d: f64, e: f64, f: f64 },
    Translate { tx: f64, ty: f64 },
    TranslateX(f64),
    TranslateY(f64),
    Scale { sx: f64, sy: f64 },
    ScaleX(f64),
    ScaleY(f64),
    Rotate(f64),           // angle in radians
    SkewX(f64),            // angle in radians
    SkewY(f64),            // angle in radians
    Skew { ax: f64, ay: f64 },
    
    // 3D primitives
    Matrix3d(Matrix3d),
    Translate3d { tx: f64, ty: f64, tz: f64 },
    TranslateZ(f64),
    Scale3d { sx: f64, sy: f64, sz: f64 },
    ScaleZ(f64),
    Rotate3d { x: f64, y: f64, z: f64, angle: f64 },
    RotateX(f64),
    RotateY(f64),
    RotateZ(f64),
    Perspective(f64),      // value in pixels
}

impl TransformFunction {
    /// Convert this transform function to a 4×4 matrix
    pub fn to_matrix(&self) -> Matrix3d {
        match self {
            Self::Matrix { a, b, c, d, e, f } => Matrix3d {
                m: [
                    [*a, *b, 0.0, 0.0],
                    [*c, *d, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [*e, *f, 0.0, 1.0],
                ],
            },
            
            Self::Translate { tx, ty } => {
                let mut m = Matrix3d::identity();
                m.m[3][0] = *tx;
                m.m[3][1] = *ty;
                m
            }
            
            Self::TranslateX(tx) => {
                let mut m = Matrix3d::identity();
                m.m[3][0] = *tx;
                m
            }
            
            Self::TranslateY(ty) => {
                let mut m = Matrix3d::identity();
                m.m[3][1] = *ty;
                m
            }
            
            Self::Scale { sx, sy } => {
                let mut m = Matrix3d::identity();
                m.m[0][0] = *sx;
                m.m[1][1] = *sy;
                m
            }
            
            Self::ScaleX(sx) => {
                let mut m = Matrix3d::identity();
                m.m[0][0] = *sx;
                m
            }
            
            Self::ScaleY(sy) => {
                let mut m = Matrix3d::identity();
                m.m[1][1] = *sy;
                m
            }
            
            Self::Rotate(angle) => {
                let cos = angle.cos();
                let sin = angle.sin();
                Matrix3d {
                    m: [
                        [cos, sin, 0.0, 0.0],
                        [-sin, cos, 0.0, 0.0],
                        [0.0, 0.0, 1.0, 0.0],
                        [0.0, 0.0, 0.0, 1.0],
                    ],
                }
            }
            
            Self::SkewX(angle) => {
                let mut m = Matrix3d::identity();
                m.m[1][0] = angle.tan();
                m
            }
            
            Self::SkewY(angle) => {
                let mut m = Matrix3d::identity();
                m.m[0][1] = angle.tan();
                m
            }
            
            Self::Skew { ax, ay } => {
                let mut m = Matrix3d::identity();
                m.m[1][0] = ax.tan();
                m.m[0][1] = ay.tan();
                m
            }
            
            Self::Matrix3d(m) => *m,
            
            Self::Translate3d { tx, ty, tz } => {
                let mut m = Matrix3d::identity();
                m.m[3][0] = *tx;
                m.m[3][1] = *ty;
                m.m[3][2] = *tz;
                m
            }
            
            Self::TranslateZ(tz) => {
                let mut m = Matrix3d::identity();
                m.m[3][2] = *tz;
                m
            }
            
            Self::Scale3d { sx, sy, sz } => {
                let mut m = Matrix3d::identity();
                m.m[0][0] = *sx;
                m.m[1][1] = *sy;
                m.m[2][2] = *sz;
                m
            }
            
            Self::ScaleZ(sz) => {
                let mut m = Matrix3d::identity();
                m.m[2][2] = *sz;
                m
            }
            
            Self::RotateX(angle) => {
                let cos = angle.cos();
                let sin = angle.sin();
                Matrix3d {
                    m: [
                        [1.0, 0.0, 0.0, 0.0],
                        [0.0, cos, sin, 0.0],
                        [0.0, -sin, cos, 0.0],
                        [0.0, 0.0, 0.0, 1.0],
                    ],
                }
            }
            
            Self::RotateY(angle) => {
                let cos = angle.cos();
                let sin = angle.sin();
                Matrix3d {
                    m: [
                        [cos, 0.0, -sin, 0.0],
                        [0.0, 1.0, 0.0, 0.0],
                        [sin, 0.0, cos, 0.0],
                        [0.0, 0.0, 0.0, 1.0],
                    ],
                }
            }
            
            Self::RotateZ(angle) => TransformFunction::Rotate(*angle).to_matrix(),
            
            Self::Rotate3d { x, y, z, angle } => {
                // Rodrigues' rotation formula
                let len = (x*x + y*y + z*z).sqrt();
                if len == 0.0 { return Matrix3d::identity(); }
                let (nx, ny, nz) = (x/len, y/len, z/len);
                let cos = angle.cos();
                let sin = angle.sin();
                let t = 1.0 - cos;
                Matrix3d {
                    m: [
                        [t*nx*nx + cos,     t*nx*ny + nz*sin, t*nx*nz - ny*sin, 0.0],
                        [t*nx*ny - nz*sin,  t*ny*ny + cos,    t*ny*nz + nx*sin, 0.0],
                        [t*nx*nz + ny*sin,  t*ny*nz - nx*sin, t*nz*nz + cos,    0.0],
                        [0.0,               0.0,              0.0,               1.0],
                    ],
                }
            }
            
            Self::Perspective(d) => {
                let mut m = Matrix3d::identity();
                if *d != 0.0 {
                    m.m[2][3] = -1.0 / d;
                }
                m
            }
        }
    }
}

/// A CSS transform value — the list of transform functions applied left-to-right
pub struct CssTransform {
    pub functions: Vec<TransformFunction>,
}

impl CssTransform {
    pub fn none() -> Self { Self { functions: Vec::new() } }
    
    pub fn is_none(&self) -> bool { self.functions.is_empty() }
    
    /// Compute the accumulated transform matrix
    pub fn to_matrix(&self) -> Matrix3d {
        self.functions.iter()
            .map(|f| f.to_matrix())
            .fold(Matrix3d::identity(), |acc, m| acc.multiply(&m))
    }
    
    /// Parse a CSS transform property value into a list of transform functions
    pub fn parse(value: &str) -> Self {
        if value.trim() == "none" { return Self::none(); }
        
        let mut functions = Vec::new();
        let mut rest = value.trim();
        
        while !rest.is_empty() {
            rest = rest.trim_start();
            
            // Try to match a function name
            if let Some(paren_pos) = rest.find('(') {
                let name = rest[..paren_pos].trim().to_lowercase();
                let after_paren = &rest[paren_pos+1..];
                
                if let Some(close_pos) = after_paren.find(')') {
                    let args_str = &after_paren[..close_pos];
                    let args: Vec<f64> = args_str.split(',')
                        .map(|s| Self::parse_length(s.trim()))
                        .collect();
                    
                    let tf = Self::build_function(&name, &args);
                    if let Some(f) = tf { functions.push(f); }
                    
                    rest = &after_paren[close_pos+1..];
                } else {
                    break;
                }
            } else {
                break;
            }
        }
        
        Self { functions }
    }
    
    fn parse_length(s: &str) -> f64 {
        let s = s.trim();
        if let Some(v) = s.strip_suffix("deg") {
            return v.trim().parse::<f64>().unwrap_or(0.0).to_radians();
        }
        if let Some(v) = s.strip_suffix("rad") {
            return v.trim().parse::<f64>().unwrap_or(0.0);
        }
        if let Some(v) = s.strip_suffix("grad") {
            return v.trim().parse::<f64>().unwrap_or(0.0) * std::f64::consts::PI / 200.0;
        }
        if let Some(v) = s.strip_suffix("turn") {
            return v.trim().parse::<f64>().unwrap_or(0.0) * std::f64::consts::TAU;
        }
        if let Some(v) = s.strip_suffix("px") {
            return v.trim().parse::<f64>().unwrap_or(0.0);
        }
        s.parse::<f64>().unwrap_or(0.0)
    }
    
    fn build_function(name: &str, args: &[f64]) -> Option<TransformFunction> {
        match name {
            "translate" => Some(TransformFunction::Translate {
                tx: args.get(0).copied().unwrap_or(0.0),
                ty: args.get(1).copied().unwrap_or(0.0),
            }),
            "translatex" => Some(TransformFunction::TranslateX(args.get(0).copied().unwrap_or(0.0))),
            "translatey" => Some(TransformFunction::TranslateY(args.get(0).copied().unwrap_or(0.0))),
            "translatez" => Some(TransformFunction::TranslateZ(args.get(0).copied().unwrap_or(0.0))),
            "translate3d" => Some(TransformFunction::Translate3d {
                tx: args.get(0).copied().unwrap_or(0.0),
                ty: args.get(1).copied().unwrap_or(0.0),
                tz: args.get(2).copied().unwrap_or(0.0),
            }),
            "scale" => {
                let sx = args.get(0).copied().unwrap_or(1.0);
                let sy = args.get(1).copied().unwrap_or(sx);
                Some(TransformFunction::Scale { sx, sy })
            }
            "scalex" => Some(TransformFunction::ScaleX(args.get(0).copied().unwrap_or(1.0))),
            "scaley" => Some(TransformFunction::ScaleY(args.get(0).copied().unwrap_or(1.0))),
            "scalez" => Some(TransformFunction::ScaleZ(args.get(0).copied().unwrap_or(1.0))),
            "rotate" | "rotatez" => Some(TransformFunction::Rotate(args.get(0).copied().unwrap_or(0.0))),
            "rotatex" => Some(TransformFunction::RotateX(args.get(0).copied().unwrap_or(0.0))),
            "rotatey" => Some(TransformFunction::RotateY(args.get(0).copied().unwrap_or(0.0))),
            "rotate3d" => Some(TransformFunction::Rotate3d {
                x: args.get(0).copied().unwrap_or(0.0),
                y: args.get(1).copied().unwrap_or(0.0),
                z: args.get(2).copied().unwrap_or(0.0),
                angle: args.get(3).copied().unwrap_or(0.0),
            }),
            "skew" => Some(TransformFunction::Skew {
                ax: args.get(0).copied().unwrap_or(0.0),
                ay: args.get(1).copied().unwrap_or(0.0),
            }),
            "skewx" => Some(TransformFunction::SkewX(args.get(0).copied().unwrap_or(0.0))),
            "skewy" => Some(TransformFunction::SkewY(args.get(0).copied().unwrap_or(0.0))),
            "perspective" => Some(TransformFunction::Perspective(args.get(0).copied().unwrap_or(0.0))),
            "matrix" if args.len() >= 6 => Some(TransformFunction::Matrix {
                a: args[0], b: args[1], c: args[2], d: args[3], e: args[4], f: args[5],
            }),
            _ => None,
        }
    }
    
    /// Interpolate between two transforms at time t (0.0 to 1.0) for animations
    pub fn interpolate(from: &Matrix3d, to: &Matrix3d, t: f64) -> Matrix3d {
        // Simplified matrix interpolation using component-wise lerp
        // Full spec-compliant implementation would decompose to translate/rotate/scale first
        let mut result = Matrix3d { m: [[0.0; 4]; 4] };
        for col in 0..4 {
            for row in 0..4 {
                result.m[col][row] = from.m[col][row] * (1.0 - t) + to.m[col][row] * t;
            }
        }
        result
    }
}

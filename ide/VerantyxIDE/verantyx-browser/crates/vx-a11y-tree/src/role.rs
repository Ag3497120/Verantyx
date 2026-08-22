//! ARIA Roles and States specifications
//!
//! Provides the semantic taxonomy used to compile Chrome-scale Accessibility Trees.

use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum A11yRole {
    Alert,
    AlertDialog,
    Button,
    Checkbox,
    Dialog,
    GridCell,
    Link,
    Log,
    Marquee,
    MenuItem,
    MenuItemCheckbox,
    MenuItemRadio,
    Option,
    ProgressBar,
    Radio,
    Scrollbar,
    Slider,
    SpinButton,
    Status,
    Switch,
    Tab,
    TabPanel,
    Textbox,
    Timer,
    Tooltip,
    TreeItem,
    ComboBox,
    Grid,
    Listbox,
    Menu,
    MenuBar,
    Radiogroup,
    TabList,
    Tree,
    TreeGrid,
    Article,
    Cell,
    ColumnHeader,
    Definition,
    Directory,
    Document,
    Feed,
    Figure,
    Group,
    Heading,
    Img,
    List,
    ListItem,
    Math,
    None,
    Note,
    Presentation,
    Region,
    Row,
    RowGroup,
    RowHeader,
    Separator,
    Table,
    Term,
    TextLeaf,
    Application,
    Banner,
    Complementary,
    ContentInfo,
    Form,
    Main,
    Navigation,
    Search,
    GenericContainer,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct A11yState {
    pub disabled: bool,
    pub hidden: bool,
    pub checked: Option<bool>,
    pub expanded: Option<bool>,
    pub selected: Option<bool>,
    pub invalid: bool,
}

impl Default for A11yState {
    fn default() -> Self {
        Self {
            disabled: false,
            hidden: false,
            checked: None,
            expanded: None,
            selected: None,
            invalid: false,
        }
    }
}
